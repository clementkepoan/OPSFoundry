from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from pydantic import BaseModel, Field

from core.documents.ocr import OCR_SUCCESS_STATUSES
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
        extraction_settings = _read_extraction_settings(work_item)
        warnings: list[str] = []

        if not document_text:
            failed_state = "ocr_failed" if work_item.ocr_status not in OCR_SUCCESS_STATUSES else "extraction_failed"
            updated_item = work_item.model_copy(
                update={
                    "state": failed_state,
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
                    system_prompt=_build_extraction_prompt(
                        workflow.extraction_system_prompt(),
                        extraction_settings,
                    ),
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
                        "state": "extraction_failed",
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

        canonical_payload = extracted_model.model_dump(mode="json")
        canonical_payload = _apply_line_item_policy(
            payload=canonical_payload,
            include_line_items=bool(extraction_settings.get("include_line_items", True)),
        )
        canonical_payload, conversion_warning = _convert_payload_currency(
            payload=canonical_payload,
            target_currency=extraction_settings.get("target_currency"),
        )
        if conversion_warning:
            warnings.append(conversion_warning)
        payload = _filter_payload_by_selected_fields(
            payload=canonical_payload,
            selected_fields=extraction_settings.get("selected_fields"),
        )
        updated_item = work_item.model_copy(
            update={
                "state": "extracted",
                "extraction_status": "succeeded",
                "extraction_backend": backend,
                "extracted_data": payload,
                "extraction_error": None,
                "metadata": {
                    **work_item.metadata,
                    "extraction_settings": extraction_settings,
                    "canonical_extracted_data": canonical_payload,
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


EXTRACTION_FIELDS = {
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "currency",
    "subtotal",
    "tax_amount",
    "total_amount",
    "payment_terms",
    "line_items",
}

USD_PER_UNIT = {
    "USD": Decimal("1"),
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
    "JPY": Decimal("0.0068"),
    "TWD": Decimal("0.031"),
    "IDR": Decimal("0.000064"),
    "SGD": Decimal("0.74"),
    "AUD": Decimal("0.66"),
    "CAD": Decimal("0.74"),
    "MYR": Decimal("0.22"),
    "THB": Decimal("0.028"),
    "CNY": Decimal("0.14"),
}


def _read_extraction_settings(work_item: WorkItem) -> dict[str, Any]:
    settings = work_item.metadata.get("extraction_settings", {})
    if not isinstance(settings, dict):
        return {}

    selected_fields = settings.get("selected_fields")
    if isinstance(selected_fields, list):
        filtered_fields = [field for field in selected_fields if field in EXTRACTION_FIELDS]
    else:
        filtered_fields = []

    target_currency = settings.get("target_currency")
    if isinstance(target_currency, str):
        target_currency = target_currency.upper().strip()
    else:
        target_currency = None

    source_language = settings.get("source_language")
    if isinstance(source_language, str):
        source_language = source_language.strip().lower()
    else:
        source_language = "auto"

    include_line_items = bool(settings.get("include_line_items", True))
    if not include_line_items and "line_items" in filtered_fields:
        filtered_fields = [field for field in filtered_fields if field != "line_items"]

    return {
        "selected_fields": filtered_fields,
        "target_currency": target_currency,
        "source_language": source_language or "auto",
        "include_line_items": include_line_items,
    }


def _build_extraction_prompt(base_prompt: str, extraction_settings: dict[str, Any]) -> str:
    selected_fields = extraction_settings.get("selected_fields") or sorted(EXTRACTION_FIELDS)
    source_language = extraction_settings.get("source_language", "auto")
    target_currency = extraction_settings.get("target_currency")
    include_line_items = extraction_settings.get("include_line_items", True)
    line_item_instruction = (
        "Extract line items with description, quantity, unit_price, and amount."
        if include_line_items
        else "Line items may be left as a single summarized row."
    )

    return "\n".join(
        [
            base_prompt,
            "Extraction profile:",
            f"- Preferred source language: {source_language}",
            f"- Requested fields: {', '.join(selected_fields)}",
            f"- {line_item_instruction}",
            (
                f"- Normalize money fields to target currency {target_currency} in output."
                if target_currency
                else "- Keep money fields in detected invoice currency."
            ),
            "- If invoice text is not English, translate semantic labels to English keys while preserving values.",
        ]
    )


def _convert_payload_currency(
    payload: dict[str, Any],
    target_currency: str | None,
) -> tuple[dict[str, Any], str | None]:
    source_currency = str(payload.get("currency") or "").upper()
    if not target_currency or not source_currency:
        return payload, None
    target_currency = target_currency.upper()
    if source_currency == target_currency:
        return payload, None

    conversion_factor, provider = _conversion_factor(source_currency, target_currency)
    if conversion_factor is None:
        return payload, f"Currency conversion skipped for unsupported pair {source_currency}->{target_currency}."
    converted = dict(payload)
    for key in ("subtotal", "tax_amount", "total_amount"):
        converted[key] = _convert_decimal_string(converted.get(key), conversion_factor)

    line_items = converted.get("line_items")
    if isinstance(line_items, list):
        updated_items: list[dict[str, Any]] = []
        for line in line_items:
            if not isinstance(line, dict):
                continue
            updated_items.append(
                {
                    **line,
                    "unit_price": _convert_decimal_string(line.get("unit_price"), conversion_factor),
                    "amount": _convert_decimal_string(line.get("amount"), conversion_factor),
                }
            )
        converted["line_items"] = updated_items

    converted["currency"] = target_currency
    return converted, f"Converted amounts from {source_currency} to {target_currency} ({provider})."


def _apply_line_item_policy(payload: dict[str, Any], include_line_items: bool) -> dict[str, Any]:
    if include_line_items:
        return payload

    collapsed = dict(payload)
    subtotal = str(payload.get("subtotal", "0"))
    collapsed["line_items"] = [
        {
            "description": "Collapsed invoice total",
            "quantity": "1",
            "unit_price": subtotal,
            "amount": subtotal,
            "account_code": None,
            "cost_center": None,
        }
    ]
    return collapsed


def _convert_decimal_string(value: Any, factor: Decimal) -> str:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    converted = (decimal_value * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return str(converted)


def _conversion_factor(source_currency: str, target_currency: str) -> tuple[Decimal | None, str]:
    live = _live_conversion_factor(source_currency, target_currency)
    if live is not None:
        return live, "live_api"

    source_rate = USD_PER_UNIT.get(source_currency)
    target_rate = USD_PER_UNIT.get(target_currency)
    if source_rate is None or target_rate is None:
        return None, "unavailable"
    return source_rate / target_rate, "static_fallback"


def _live_conversion_factor(source_currency: str, target_currency: str) -> Decimal | None:
    try:
        with urlopen(
            f"https://open.er-api.com/v6/latest/{source_currency}",
            timeout=2.5,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        return None

    rates = payload.get("rates")
    if not isinstance(rates, dict):
        return None
    target_rate = rates.get(target_currency)
    if target_rate is None:
        return None

    try:
        return Decimal(str(target_rate))
    except (InvalidOperation, ValueError):
        return None


def _filter_payload_by_selected_fields(
    payload: dict[str, Any],
    selected_fields: object,
) -> dict[str, Any]:
    if not isinstance(selected_fields, list) or not selected_fields:
        return payload

    allowed = {field for field in selected_fields if isinstance(field, str)}
    if payload.get("explanation") is not None:
        allowed.add("explanation")
    return {key: value for key, value in payload.items() if key in allowed}
