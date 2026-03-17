from typing import Any

from workflows.invoice_autoposting.schemas import AccountingEntry


def build_export_rows(entry: AccountingEntry) -> list[dict[str, Any]]:
    return [
        {
            "vendor_name": entry.vendor_name,
            "invoice_number": entry.invoice_number,
            "invoice_date": entry.invoice_date.isoformat(),
            "currency": entry.currency,
            "line_description": line.description,
            "quantity": str(line.quantity),
            "unit_price": str(line.unit_price),
            "amount": str(line.amount),
            "line_subtotal": str(line.amount),
            "account_code": line.account_code or "",
            "cost_center": line.cost_center or "",
            "subtotal": str(entry.subtotal),
            "tax_amount": str(entry.tax_amount),
            "total_amount": str(entry.total_amount),
            "payment_terms": entry.payment_terms or "",
        }
        for line in entry.line_items
    ]
