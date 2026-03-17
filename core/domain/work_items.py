from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from core.documents.ocr import OCRResult
from core.documents.storage import StoredDocument


class WorkItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_name: str
    category: str = "uncategorized"
    state: str
    document_id: str
    filename: str
    content_type: str
    object_key: str
    document_sha256: str
    ocr_status: str
    ocr_backend: str | None = None
    ocr_text: str | None = None
    ocr_text_preview: str | None = None
    extraction_status: str = "pending"
    extraction_backend: str | None = None
    extracted_data: dict[str, Any] | None = None
    extraction_error: str | None = None
    validation_status: str = "pending"
    validation_results: list[dict[str, Any]] = Field(default_factory=list)
    anomaly_flags: list[dict[str, Any]] = Field(default_factory=list)
    review_status: str = "pending"
    review_notes: str | None = None
    review_history: list[dict[str, Any]] = Field(default_factory=list)
    export_status: str = "pending"
    exported_artifact: dict[str, Any] | None = None
    export_history: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_document(
        cls,
        workflow_name: str,
        category: str,
        initial_state: str,
        document: StoredDocument,
        ocr_result: OCRResult,
        metadata: dict[str, Any] | None = None,
    ) -> "WorkItem":
        metadata_payload = dict(metadata or {})
        metadata_payload["ocr_warnings"] = list(ocr_result.warnings)
        return cls(
            workflow_name=workflow_name,
            category=category,
            state=initial_state,
            document_id=document.id,
            filename=document.filename,
            content_type=document.content_type,
            object_key=document.object_key,
            document_sha256=document.sha256,
            ocr_status=ocr_result.status,
            ocr_backend=ocr_result.backend,
            ocr_text=ocr_result.extracted_text or None,
            ocr_text_preview=ocr_result.extracted_text[:500] or None,
            metadata=metadata_payload,
        )
