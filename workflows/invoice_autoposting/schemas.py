from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class DocumentUpload(BaseModel):
    filename: str
    content_type: str
    source: str = "upload"


class InvoiceLineItem(BaseModel):
    description: str
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal
    amount: Decimal
    account_code: str | None = None
    cost_center: str | None = None


class AccountingEntry(BaseModel):
    vendor_name: str
    invoice_number: str
    invoice_date: date
    currency: str = "USD"
    subtotal: Decimal
    tax_amount: Decimal = Field(default=Decimal("0"))
    total_amount: Decimal
    line_items: list[InvoiceLineItem]
    payment_terms: str | None = None
    explanation: str | None = None
