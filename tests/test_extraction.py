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
