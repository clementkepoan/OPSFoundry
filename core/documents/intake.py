from pydantic import BaseModel
from typing import BinaryIO, Protocol

from core.documents.ocr import OCRProcessingError, OCRResult, OCRService, OCR_SUCCESS_STATUSES
from core.documents.storage import LocalObjectStore, StoredDocument
from core.domain.work_items import WorkItem


class WorkItemRepository(Protocol):
    def save(self, work_item: WorkItem) -> WorkItem:
        ...


class IntakeReceipt(BaseModel):
    document: StoredDocument
    work_item: WorkItem
    ocr: OCRResult


class DocumentIntakeService:
    def __init__(
        self,
        object_store: LocalObjectStore,
        work_item_repository: WorkItemRepository,
        ocr_service: OCRService,
    ) -> None:
        self.object_store = object_store
        self.work_item_repository = work_item_repository
        self.ocr_service = ocr_service

    def upload_document(
        self,
        workflow_name: str,
        category: str,
        initial_state: str,
        filename: str,
        content_type: str,
        source: BinaryIO,
        metadata: dict[str, object] | None = None,
    ) -> IntakeReceipt:
        ocr_consumer = self.ocr_service.create_consumer(content_type)
        document: StoredDocument | None = None

        try:
            document = self.object_store.save_document_stream(
                workflow_name=workflow_name,
                filename=filename,
                content_type=content_type,
                source=source,
                on_chunk=ocr_consumer.consume,
            )
            ocr_result = ocr_consumer.finalize(self.object_store.resolve_path(document))
            if ocr_result.status not in OCR_SUCCESS_STATUSES:
                raise OCRProcessingError(
                    backend=ocr_result.backend,
                    status=ocr_result.status,
                    warnings=ocr_result.warnings,
                )
            work_item = WorkItem.from_document(
                workflow_name=workflow_name,
                category=category,
                initial_state=initial_state,
                document=document,
                ocr_result=ocr_result,
                metadata=metadata,
            )
            self.work_item_repository.save(work_item)
            return IntakeReceipt(document=document, work_item=work_item, ocr=ocr_result)
        except Exception:
            if document is not None:
                self.object_store.delete_document(document)
            raise
