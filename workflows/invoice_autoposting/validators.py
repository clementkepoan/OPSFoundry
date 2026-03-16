from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from workflows.invoice_autoposting.schemas import AccountingEntry


class ValidationResult(BaseModel):
    name: str
    passed: bool
    message: str | None = None
    details: dict[str, str] = Field(default_factory=dict)


def totals_match(entry: AccountingEntry) -> ValidationResult:
    computed_total = entry.subtotal + entry.tax_amount
    passed = computed_total == entry.total_amount
    return ValidationResult(
        name="totals_match",
        passed=passed,
        message=None if passed else "Subtotal plus tax does not match total amount.",
        details={
            "expected_total": str(computed_total),
            "reported_total": str(entry.total_amount),
        },
    )


def required_fields_present(entry: AccountingEntry) -> ValidationResult:
    required_fields = {
        "vendor_name": entry.vendor_name,
        "invoice_number": entry.invoice_number,
        "currency": entry.currency,
    }
    missing = [field for field, value in required_fields.items() if not value]
    return ValidationResult(
        name="required_fields_present",
        passed=not missing,
        message=None if not missing else "Required invoice fields are missing.",
        details={"missing_fields": ", ".join(missing)},
    )


def valid_date(entry: AccountingEntry) -> ValidationResult:
    passed = entry.invoice_date <= date.today()
    return ValidationResult(
        name="valid_date",
        passed=passed,
        message=None if passed else "Invoice date cannot be in the future.",
    )


def run_validators(entry: AccountingEntry) -> list[ValidationResult]:
    return [
        totals_match(entry),
        required_fields_present(entry),
        valid_date(entry),
    ]
