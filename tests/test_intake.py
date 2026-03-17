import io
from pathlib import Path

import pytest

from core.documents.ocr import OCRService
from core.documents.intake import DocumentIntakeService
from core.documents.storage import LocalObjectStore
from core.persistence.work_items import FileWorkItemRepository


class FailingWorkItemRepository(FileWorkItemRepository):
    def save(self, work_item):
        raise RuntimeError("simulated persistence failure")


def test_intake_rolls_back_document_on_work_item_failure(tmp_path: Path) -> None:
    object_store = LocalObjectStore(tmp_path / "documents")
    repository = FailingWorkItemRepository(tmp_path / "work_items")
    service = DocumentIntakeService(
        object_store=object_store,
        work_item_repository=repository,
        ocr_service=OCRService(),
    )

    with pytest.raises(RuntimeError, match="simulated persistence failure"):
        service.upload_document(
            workflow_name="invoice_autoposting",
            category="office_supplies",
            initial_state="uploaded",
            filename="invoice.txt",
            content_type="text/plain",
            source=io.BytesIO(b"invoice body"),
        )

    assert (tmp_path / "documents" / "_meta").exists()
    assert (tmp_path / "documents" / "invoice_autoposting").exists()
    assert not list((tmp_path / "documents" / "_meta").glob("*.json"))
    assert not list((tmp_path / "documents" / "invoice_autoposting").glob("*"))
