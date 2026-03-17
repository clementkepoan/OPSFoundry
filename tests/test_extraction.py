import asyncio

from core.config.settings import Settings
from core.domain.work_items import WorkItem
from core.runtime.engine import LangChainWorkflowEngine
from core.workflows.extraction import StructuredExtractionService
from workflows.invoice_autoposting.workflow import get_workflow


def test_invoice_workflow_fallback_extracts_required_fields() -> None:
    workflow = get_workflow()
    result = workflow.fallback_extract(
        "\n".join(
            [
                "Acme Office Supply",
                "Invoice Number: INV-1001",
                "Invoice Date: 2025-01-15",
                "Currency: USD",
                "Subtotal: 120.00",
                "Tax: 5.50",
                "Total: 125.50",
            ]
        )
    )

    assert result.vendor_name == "Acme Office Supply"
    assert result.invoice_number == "INV-1001"
    assert str(result.total_amount) == "125.50"


def test_extraction_sets_ocr_failed_state_when_ocr_text_is_missing() -> None:
    workflow = get_workflow()
    service = StructuredExtractionService(
        engine=LangChainWorkflowEngine(
            Settings(
                ocr_warmup_on_startup=False,
                ocr_warmup_strict=False,
            )
        )
    )
    work_item = WorkItem(
        workflow_name="invoice_autoposting",
        state="uploaded",
        document_id="doc-1",
        filename="missing-ocr.png",
        content_type="image/png",
        object_key="invoice_autoposting/doc-1_missing-ocr.png",
        document_sha256="sha",
        ocr_status="backend_unavailable",
        ocr_backend="google_vision",
        ocr_text=None,
        ocr_text_preview=None,
    )

    receipt = asyncio.run(service.extract_work_item(workflow, work_item))

    assert receipt.extraction.status == "failed"
    assert receipt.work_item.state == "ocr_failed"
    assert receipt.work_item.extraction_error == "No OCR text is available for extraction."


def test_extraction_applies_selected_fields_and_keeps_canonical_payload() -> None:
    workflow = get_workflow()
    service = StructuredExtractionService(
        engine=LangChainWorkflowEngine(
            Settings(
                ocr_warmup_on_startup=False,
                ocr_warmup_strict=False,
            )
        )
    )
    work_item = WorkItem(
        workflow_name="invoice_autoposting",
        category="office_supplies",
        state="uploaded",
        document_id="doc-2",
        filename="invoice.txt",
        content_type="text/plain",
        object_key="invoice_autoposting/doc-2_invoice.txt",
        document_sha256="sha",
        ocr_status="text_extracted",
        ocr_backend="plain_text",
        ocr_text="\n".join(
            [
                "Acme Office Supply",
                "Invoice Number: INV-2001",
                "Invoice Date: 2025-01-15",
                "Currency: USD",
                "Subtotal: 100.00",
                "Tax: 10.00",
                "Total: 110.00",
            ]
        ),
        ocr_text_preview=None,
        metadata={
            "extraction_settings": {
                "selected_fields": ["invoice_number", "total_amount"],
                "include_line_items": False,
                "target_currency": "EUR",
                "source_language": "auto",
            }
        },
    )

    receipt = asyncio.run(service.extract_work_item(workflow, work_item))

    assert receipt.extraction.status == "succeeded"
    assert isinstance(receipt.work_item.extracted_data, dict)
    assert "invoice_number" in receipt.work_item.extracted_data
    assert "total_amount" in receipt.work_item.extracted_data
    assert "subtotal" not in receipt.work_item.extracted_data

    canonical = receipt.work_item.metadata.get("canonical_extracted_data")
    assert isinstance(canonical, dict)
    assert canonical["currency"] == "EUR"
    assert canonical["total_amount"] != "110.00"
