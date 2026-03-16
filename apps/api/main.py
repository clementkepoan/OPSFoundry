from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

from core.persistence.audit import SQLAuditRepository
from core.runtime.audit import AuditService
from core.config.settings import Settings, get_settings
from core.persistence.session import build_engine, build_session_factory, init_database
from core.documents.ocr import OCRProcessingError, OCRService
from core.runtime.evaluation import EvaluationService
from core.workflows.extraction import StructuredExtractionService
from core.workflows.exports import ExportService
from core.documents.intake import DocumentIntakeService
from core.runtime.observability import ObservabilityService
from core.runtime.engine import LangChainWorkflowEngine
from core.runtime.request_guard import (
    build_request_guard,
    build_upload_request_key,
    build_work_item_request_key,
)
from core.workflows.review import ReviewService
from core.documents.storage import LocalObjectStore
from core.workflows.validation import ValidationService
from core.persistence.work_items_sql import SQLWorkItemRepository
from core.workflows.registry import get_registry


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    registry = get_registry()
    engine = LangChainWorkflowEngine(settings=active_settings)
    db_engine = build_engine(active_settings)
    init_database(db_engine)
    session_factory = build_session_factory(db_engine)
    object_store = LocalObjectStore(active_settings.document_storage_dir)
    work_item_repository = SQLWorkItemRepository(session_factory=session_factory)
    ocr_service = OCRService(
        google_application_credentials=active_settings.google_application_credentials,
        max_pdf_pages=active_settings.ocr_pdf_max_pages,
    )
    if active_settings.ocr_warmup_on_startup:
        warmup_result = ocr_service.warmup()
        if warmup_result.status != "ready" and active_settings.ocr_warmup_strict:
            detail = "; ".join(warmup_result.warnings) or "OCR warmup failed."
            raise RuntimeError(detail)
    intake_service = DocumentIntakeService(
        object_store=object_store,
        work_item_repository=work_item_repository,
        ocr_service=ocr_service,
    )
    extraction_service = StructuredExtractionService(engine=engine)
    validation_service = ValidationService()
    review_service = ReviewService()
    export_service = ExportService(root_dir=active_settings.export_storage_dir)
    audit_service = AuditService(repository=SQLAuditRepository(session_factory=session_factory))
    observability_service = ObservabilityService(settings=active_settings, audit_service=audit_service)
    evaluation_service = EvaluationService(
        eval_sets_root=Path(__file__).resolve().parents[2] / "mlops" / "eval_sets",
        engine=engine,
        observability=observability_service,
    )
    request_guard = build_request_guard(active_settings)

    app = FastAPI(
        title=active_settings.app_name,
        version="0.1.0",
        summary="Workflow-agnostic gateway for OPSFoundry",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = active_settings
    app.state.registry = registry
    app.state.engine = engine
    app.state.db_engine = db_engine
    app.state.session_factory = session_factory
    app.state.object_store = object_store
    app.state.work_item_repository = work_item_repository
    app.state.ocr_service = ocr_service
    app.state.intake_service = intake_service
    app.state.extraction_service = extraction_service
    app.state.validation_service = validation_service
    app.state.review_service = review_service
    app.state.export_service = export_service
    app.state.audit_service = audit_service
    app.state.observability_service = observability_service
    app.state.evaluation_service = evaluation_service
    app.state.request_guard = request_guard

    def claim_request(request: Request, key: str) -> None:
        ttl_seconds = request.app.state.settings.duplicate_request_ttl_seconds
        claimed = request.app.state.request_guard.claim(key, ttl_seconds)
        if not claimed:
            raise HTTPException(
                status_code=409,
                detail="A duplicate request is already in progress or was completed recently.",
            )

    async def persist_extraction(request: Request, workflow, work_item):
        receipt = await request.app.state.extraction_service.extract_work_item(workflow, work_item)
        request.app.state.work_item_repository.save(receipt.work_item)
        request.app.state.observability_service.record_workflow_event(
            event_type="fields_extracted",
            workflow_name=workflow.metadata.name,
            work_item=receipt.work_item,
            payload={"backend": receipt.extraction.backend, "status": receipt.extraction.status},
        )
        return receipt

    def persist_validation(request: Request, workflow, work_item):
        updated_item, run = request.app.state.validation_service.validate_work_item(workflow, work_item)
        request.app.state.work_item_repository.save(updated_item)
        request.app.state.observability_service.record_workflow_event(
            event_type="fields_validated",
            workflow_name=workflow.metadata.name,
            work_item=updated_item,
            payload={
                "status": run.status,
                "validation_results": [result.model_dump(mode="json") for result in run.results],
                "anomalies": [flag.model_dump(mode="json") for flag in run.anomalies],
            },
        )

        artifact = None
        response_item = updated_item
        if run.status == "passed":
            response_item, artifact = persist_export(
                request=request,
                workflow=workflow,
                work_item=updated_item,
                export_format="csv",
                error_status=500,
            )
        return response_item, run, artifact

    def persist_export(
        request: Request,
        workflow,
        work_item,
        export_format: str = "csv",
        error_status: int = 400,
    ):
        try:
            updated_item, artifact = request.app.state.export_service.export_work_item(
                workflow=workflow,
                work_item=work_item,
                export_format=export_format,
            )
        except ValueError as exc:
            raise HTTPException(status_code=error_status, detail=str(exc)) from exc

        request.app.state.work_item_repository.save(updated_item)
        request.app.state.observability_service.record_workflow_event(
            event_type="work_item_exported",
            workflow_name=workflow.metadata.name,
            work_item=updated_item,
            payload=artifact.model_dump(mode="json"),
        )
        return updated_item, artifact

    @app.get("/", tags=["system"])
    def root(request: Request) -> dict[str, str]:
        return {
            "name": request.app.state.settings.app_name,
            "environment": request.app.state.settings.app_env,
            "status": "ok",
        }

    @app.get("/health", tags=["system"])
    def healthcheck(request: Request) -> dict[str, object]:
        return {
            "status": "ok",
            "langchain_ready": request.app.state.engine.is_ready(),
            "registered_workflows": request.app.state.registry.names(),
        }

    @app.get("/api/v1/workflows", tags=["workflows"])
    def list_workflows(request: Request) -> list[dict[str, object]]:
        return [
            workflow.metadata.model_dump(mode="json")
            for workflow in request.app.state.registry.all()
        ]

    @app.get("/api/v1/workflows/{workflow_name}", tags=["workflows"])
    def get_workflow(workflow_name: str, request: Request) -> dict[str, object]:
        try:
            workflow = request.app.state.registry.get(workflow_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown workflow '{workflow_name}'") from exc

        return {
            "metadata": workflow.metadata.model_dump(mode="json"),
            "step_pipeline": workflow.step_pipeline(),
            "runtime": request.app.state.engine.describe_runtime(),
        }

    @app.post("/api/v1/workflows/{workflow_name}/documents", status_code=201, tags=["documents"])
    async def upload_document(
        workflow_name: str,
        request: Request,
        file: UploadFile = File(...),
    ) -> dict[str, object]:
        try:
            workflow = request.app.state.registry.get(workflow_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown workflow '{workflow_name}'") from exc

        await file.seek(0)
        source = file.file
        source.seek(0, 2)
        size_bytes = source.tell()
        source.seek(0)
        if not size_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        request_key = build_upload_request_key(
            workflow_name=workflow.metadata.name,
            filename=file.filename or "upload.bin",
            content_type=file.content_type or "application/octet-stream",
            size_bytes=size_bytes,
            client_key=request.headers.get("X-Idempotency-Key"),
        )
        claim_request(request, request_key)

        try:
            receipt = request.app.state.intake_service.upload_document(
                workflow_name=workflow.metadata.name,
                initial_state=workflow.metadata.states[0] if workflow.metadata.states else "uploaded",
                filename=file.filename or "upload.bin",
                content_type=file.content_type or "application/octet-stream",
                source=source,
            )
            request.app.state.observability_service.record_workflow_event(
                event_type="document_uploaded",
                workflow_name=workflow.metadata.name,
                work_item=receipt.work_item,
                payload={"document_id": receipt.document.id, "ocr_backend": receipt.ocr.backend},
            )
            extraction_receipt = await persist_extraction(request, workflow, receipt.work_item)
            validation = None
            artifact = None
            response_item = extraction_receipt.work_item
            if extraction_receipt.extraction.status == "succeeded":
                response_item, validation, artifact = persist_validation(
                    request,
                    workflow,
                    extraction_receipt.work_item,
                )
            return {
                "document": receipt.document.model_dump(mode="json"),
                "ocr": receipt.ocr.model_dump(mode="json"),
                "work_item": response_item.model_dump(mode="json"),
                "extraction": extraction_receipt.extraction.model_dump(mode="json"),
                "validation": validation.model_dump(mode="json") if validation else None,
                "artifact": artifact.model_dump(mode="json") if artifact else None,
            }
        except OCRProcessingError as exc:
            request.app.state.request_guard.clear(request_key)
            if exc.status == "backend_unavailable":
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception:
            request.app.state.request_guard.clear(request_key)
            raise

    @app.get("/api/v1/work-items", tags=["work-items"])
    def list_work_items(request: Request, workflow_name: str | None = None) -> list[dict[str, object]]:
        return [
            work_item.model_dump(mode="json")
            for work_item in request.app.state.work_item_repository.list(workflow_name=workflow_name)
        ]

    @app.get("/api/v1/work-items/{work_item_id}", tags=["work-items"])
    def get_work_item(work_item_id: str, request: Request) -> dict[str, object]:
        try:
            work_item = request.app.state.work_item_repository.get(work_item_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown work item '{work_item_id}'") from exc

        return work_item.model_dump(mode="json")

    @app.delete("/api/v1/work-items/{work_item_id}", tags=["work-items"])
    def delete_work_item(work_item_id: str, request: Request) -> dict[str, object]:
        try:
            work_item = request.app.state.work_item_repository.get(work_item_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown work item '{work_item_id}'") from exc

        request.app.state.work_item_repository.delete(work_item_id)

        try:
            document = request.app.state.object_store.get_document(work_item.document_id)
            request.app.state.object_store.delete_document(document)
        except KeyError:
            pass

        request.app.state.observability_service.record_workflow_event(
            event_type="work_item_deleted",
            workflow_name=work_item.workflow_name,
            work_item=work_item,
            payload={"deleted_document_id": work_item.document_id},
        )
        return {
            "deleted_work_item_id": work_item_id,
            "deleted_document_id": work_item.document_id,
        }

    @app.post("/api/v1/work-items/{work_item_id}/extract", tags=["extract"])
    async def extract_work_item(work_item_id: str, request: Request) -> dict[str, object]:
        try:
            work_item = request.app.state.work_item_repository.get(work_item_id)
            workflow = request.app.state.registry.get(work_item.workflow_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown work item '{work_item_id}'") from exc

        request_key = build_work_item_request_key(
            action="extract",
            work_item_id=work_item_id,
            client_key=request.headers.get("X-Idempotency-Key"),
        )
        claim_request(request, request_key)

        try:
            receipt = await persist_extraction(request, workflow, work_item)
            return receipt.model_dump(mode="json")
        except Exception:
            request.app.state.request_guard.clear(request_key)
            raise

    @app.post("/api/v1/work-items/{work_item_id}/validate", tags=["validate"])
    def validate_work_item(work_item_id: str, request: Request) -> dict[str, object]:
        try:
            work_item = request.app.state.work_item_repository.get(work_item_id)
            workflow = request.app.state.registry.get(work_item.workflow_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown work item '{work_item_id}'") from exc

        request_key = build_work_item_request_key(
            action="validate",
            work_item_id=work_item_id,
            client_key=request.headers.get("X-Idempotency-Key"),
        )
        claim_request(request, request_key)

        try:
            response_item, run, artifact = persist_validation(
                request=request,
                workflow=workflow,
                work_item=work_item,
            )
            return {
                "work_item": response_item.model_dump(mode="json"),
                "validation": run.model_dump(mode="json"),
                "artifact": artifact.model_dump(mode="json") if artifact else None,
            }
        except Exception:
            request.app.state.request_guard.clear(request_key)
            raise

    @app.get("/api/v1/review-queue", tags=["review"])
    def list_review_queue(request: Request, workflow_name: str | None = None) -> list[dict[str, object]]:
        queue = request.app.state.review_service.list_queue(
            request.app.state.work_item_repository.list(workflow_name=workflow_name),
            workflow_name=workflow_name,
        )
        return [item.model_dump(mode="json") for item in queue]

    @app.post("/api/v1/work-items/{work_item_id}/review", tags=["review"])
    def review_work_item(work_item_id: str, request: Request, payload: dict[str, object]) -> dict[str, object]:
        try:
            work_item = request.app.state.work_item_repository.get(work_item_id)
            workflow = request.app.state.registry.get(work_item.workflow_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown work item '{work_item_id}'") from exc

        action = str(payload.get("action"))
        request_key = build_work_item_request_key(
            action="review",
            work_item_id=work_item_id,
            qualifier=action,
            client_key=request.headers.get("X-Idempotency-Key"),
        )
        claim_request(request, request_key)

        try:
            updated_item = request.app.state.review_service.apply_review_action(
                workflow=workflow,
                work_item=work_item,
                action=action,
                review_notes=payload.get("review_notes") if isinstance(payload.get("review_notes"), str) else None,
                updated_data=payload.get("updated_data") if isinstance(payload.get("updated_data"), dict) else None,
            )
        except ValueError as exc:
            request.app.state.request_guard.clear(request_key)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            request.app.state.request_guard.clear(request_key)
            raise

        request.app.state.work_item_repository.save(updated_item)
        request.app.state.observability_service.record_workflow_event(
            event_type=f"review_{payload.get('action')}",
            workflow_name=workflow.metadata.name,
            work_item=updated_item,
            payload={"review_notes": updated_item.review_notes},
        )
        try:
            artifact = None
            response_item = updated_item
            if action == "approve":
                response_item, artifact = persist_export(
                    request=request,
                    workflow=workflow,
                    work_item=updated_item,
                    export_format="csv",
                    error_status=500,
                )
            return {
                "work_item": response_item.model_dump(mode="json"),
                "artifact": artifact.model_dump(mode="json") if artifact else None,
            }
        except Exception:
            request.app.state.request_guard.clear(request_key)
            raise

    @app.post("/api/v1/work-items/{work_item_id}/export", tags=["exports"])
    def export_work_item(work_item_id: str, request: Request, export_format: str = "csv") -> dict[str, object]:
        try:
            work_item = request.app.state.work_item_repository.get(work_item_id)
            workflow = request.app.state.registry.get(work_item.workflow_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown work item '{work_item_id}'") from exc

        request_key = build_work_item_request_key(
            action="export",
            work_item_id=work_item_id,
            qualifier=export_format,
            client_key=request.headers.get("X-Idempotency-Key"),
        )
        claim_request(request, request_key)

        try:
            updated_item, artifact = persist_export(
                request=request,
                workflow=workflow,
                work_item=work_item,
                export_format=export_format,
                error_status=400,
            )
            return {
                "work_item": updated_item.model_dump(mode="json"),
                "artifact": artifact.model_dump(mode="json"),
            }
        except Exception:
            request.app.state.request_guard.clear(request_key)
            raise

    @app.get("/api/v1/workflows/{workflow_name}/exports/csv/download", tags=["exports"])
    def download_workflow_csv_export(workflow_name: str, request: Request) -> FileResponse:
        try:
            request.app.state.registry.get(workflow_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown workflow '{workflow_name}'") from exc

        path = request.app.state.export_service.workflow_csv_path(workflow_name)
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"No CSV export has been generated yet for workflow '{workflow_name}'.",
            )

        return FileResponse(
            path,
            media_type="text/csv",
            filename=path.name,
        )

    @app.get("/api/v1/work-items/{work_item_id}/audit", tags=["audit"])
    def get_work_item_audit(work_item_id: str, request: Request) -> list[dict[str, object]]:
        return [
            event.model_dump(mode="json")
            for event in request.app.state.observability_service.audit_events(work_item_id=work_item_id)
        ]

    @app.get("/api/v1/observability/status", tags=["observability"])
    def get_observability_status(request: Request) -> dict[str, object]:
        status = request.app.state.observability_service.status()
        status["request_guard_backend"] = request.app.state.request_guard.backend
        status["duplicate_request_ttl_seconds"] = request.app.state.settings.duplicate_request_ttl_seconds
        return status

    @app.post("/api/v1/evals/{workflow_name}/run", tags=["observability"])
    async def run_workflow_eval(
        workflow_name: str,
        request: Request,
        mode: str = "fallback",
    ) -> dict[str, object]:
        try:
            workflow = request.app.state.registry.get(workflow_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown workflow '{workflow_name}'") from exc

        try:
            report = await request.app.state.evaluation_service.run_workflow_eval(workflow, mode=mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return report.model_dump(mode="json")

    @app.get("/api/v1/documents/{document_id}", tags=["documents"])
    def get_document(document_id: str, request: Request) -> dict[str, object]:
        try:
            document = request.app.state.object_store.get_document(document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown document '{document_id}'") from exc

        return document.model_dump(mode="json")

    @app.get("/api/v1/documents/{document_id}/download", tags=["documents"])
    def download_document(document_id: str, request: Request) -> FileResponse:
        try:
            document = request.app.state.object_store.get_document(document_id)
            path = request.app.state.object_store.resolve_path(document)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown document '{document_id}'") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Stored file for document '{document_id}' is missing") from exc

        return FileResponse(
            path,
            media_type=document.content_type,
            filename=document.filename,
        )

    return app


app = create_app()
