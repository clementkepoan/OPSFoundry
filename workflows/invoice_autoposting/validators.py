from datetime import date

from core.workflows.validation_models import AnomalyFlag, ValidationResult
from workflows.invoice_autoposting.schemas import AccountingEntry


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


def meaningful_amounts(entry: AccountingEntry) -> ValidationResult:
    passed = any(amount > 0 for amount in (entry.subtotal, entry.tax_amount, entry.total_amount))
    return ValidationResult(
        name="meaningful_amounts",
        passed=passed,
        message=None if passed else "Invoice amounts cannot all be zero.",
        details={
            "subtotal": str(entry.subtotal),
            "tax_amount": str(entry.tax_amount),
            "total_amount": str(entry.total_amount),
        },
    )


def run_validators(entry: AccountingEntry) -> list[ValidationResult]:
    return [
        totals_match(entry),
        required_fields_present(entry),
        valid_date(entry),
        meaningful_amounts(entry),
    ]


def detect_anomalies(
    entry: AccountingEntry,
    validation_results: list[ValidationResult],
) -> list[AnomalyFlag]:
    anomalies: list[AnomalyFlag] = []

    for result in validation_results:
        if not result.passed:
            anomalies.append(
                AnomalyFlag(
                    code=f"validation_{result.name}",
                    severity="high",
                    message=result.message or f"Validation '{result.name}' failed.",
                    details=result.details,
                )
            )

    if entry.total_amount >= 10000:
        anomalies.append(
            AnomalyFlag(
                code="high_value_invoice",
                severity="medium",
                message="Invoice total exceeds the high-value review threshold.",
                details={"threshold": "10000.00", "reported_total": str(entry.total_amount)},
            )
        )

    if not entry.payment_terms:
        anomalies.append(
            AnomalyFlag(
                code="missing_payment_terms",
                severity="low",
                message="Payment terms were not extracted.",
            )
        )

    return anomalies
