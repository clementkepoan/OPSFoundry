from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from core.runtime.engine import LangChainWorkflowEngine
from core.domain.work_items import WorkItem
from core.workflows.base import BaseWorkflow


class ExtractionRun(BaseModel):
    status: str
    backend: str
    output_schema: str
    payload: dict[str, Any] | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ExtractionReceipt(BaseModel):
    work_item: WorkItem
    extraction: ExtractionRun


class StructuredExtractionService:
    def __init__(self, engine: LangChainWorkflowEngine) -> None:
        self.engine = engine

    async def extract_work_item(
        self,
        workflow: BaseWorkflow,
        work_item: WorkItem,
    ) -> ExtractionReceipt:
        document_text = (work_item.ocr_text or "").strip()
        warnings: list[str] = []

        if not document_text:
            updated_item = work_item.model_copy(
                update={
                    "extraction_status": "failed",
                    "extraction_error": "No OCR text is available for extraction.",
                    "updated_at": datetime.now(UTC),
                }
            )
            return ExtractionReceipt(
                work_item=updated_item,
                extraction=ExtractionRun(
                    status="failed",
                    backend="none",
                    output_schema=workflow.metadata.output_schema,
                    error="No OCR text is available for extraction.",
                ),
            )

        extracted_model: BaseModel | None = None
        backend = "deterministic_fallback"

        if self.engine.is_ready():
            try:
                extracted_model = await self.engine.extract_structured(
                    workflow_name=workflow.metadata.name,
                    system_prompt=workflow.extraction_system_prompt(),
                    document_text=document_text,
                    output_model=workflow.output_schema_model(),
                )
                backend = "deepseek"
            except Exception as exc:
                warnings.append(f"DeepSeek extraction failed and fallback was used: {exc}")

        if extracted_model is None:
            try:
                extracted_model = workflow.fallback_extract(document_text)
            except Exception as exc:
                updated_item = work_item.model_copy(
                    update={
                        "extraction_status": "failed",
                        "extraction_backend": backend,
                        "extraction_error": str(exc),
                        "metadata": {
                            **work_item.metadata,
                            "extraction_warnings": warnings,
                        },
                        "updated_at": datetime.now(UTC),
                    }
                )
                return ExtractionReceipt(
                    work_item=updated_item,
                    extraction=ExtractionRun(
                        status="failed",
                        backend=backend,
                        output_schema=workflow.metadata.output_schema,
                        error=str(exc),
                        warnings=warnings,
                    ),
                )

        payload = extracted_model.model_dump(mode="json")
        updated_item = work_item.model_copy(
            update={
                "state": "extracted",
                "extraction_status": "succeeded",
                "extraction_backend": backend,
                "extracted_data": payload,
                "extraction_error": None,
                "metadata": {
                    **work_item.metadata,
                    "extraction_warnings": warnings,
                },
                "updated_at": datetime.now(UTC),
            }
        )
        return ExtractionReceipt(
            work_item=updated_item,
            extraction=ExtractionRun(
                status="succeeded",
                backend=backend,
                output_schema=workflow.metadata.output_schema,
                payload=payload,
                warnings=warnings,
            ),
        )
