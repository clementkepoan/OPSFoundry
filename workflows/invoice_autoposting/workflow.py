from pathlib import Path

from pydantic import BaseModel
import yaml

from core.workflows.base import BaseWorkflow, WorkflowMetadata
from workflows.invoice_autoposting.exports import build_export_rows
from workflows.invoice_autoposting.parser import extract_accounting_entry
from workflows.invoice_autoposting.prompts import EXTRACTION_SYSTEM_PROMPT
from workflows.invoice_autoposting.schemas import AccountingEntry
from workflows.invoice_autoposting.validators import detect_anomalies, run_validators

WORKFLOW_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = WORKFLOW_ROOT / "config.yaml"


class InvoiceAutopostingWorkflow(BaseWorkflow):
    def __init__(self) -> None:
        self._metadata = WorkflowMetadata(**self._load_config(), root_dir=WORKFLOW_ROOT)

    @property
    def metadata(self) -> WorkflowMetadata:
        return self._metadata

    def step_pipeline(self) -> list[str]:
        return [
            "upload_document",
            "create_work_item",
            "run_langchain_workflow",
            "extract_fields",
            "validate_fields",
            "flag_anomalies",
            "send_to_review",
            "approve_item",
            "export_entry",
        ]

    def output_schema_model(self) -> type[BaseModel]:
        return AccountingEntry

    def extraction_system_prompt(self) -> str:
        return EXTRACTION_SYSTEM_PROMPT

    def fallback_extract(self, document_text: str) -> BaseModel:
        return extract_accounting_entry(document_text)

    def validate_extracted_payload(self, extracted_model: BaseModel):
        entry = self._as_entry(extracted_model)
        return run_validators(entry)

    def detect_anomalies(self, extracted_model: BaseModel, validation_results):
        entry = self._as_entry(extracted_model)
        return detect_anomalies(entry, validation_results)

    def export_rows(self, extracted_model: BaseModel) -> list[dict[str, object]]:
        return build_export_rows(self._as_entry(extracted_model))

    @staticmethod
    def _load_config() -> dict[str, object]:
        with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)

        config["name"] = config.pop("workflow_name")
        return config

    @staticmethod
    def _as_entry(extracted_model: BaseModel) -> AccountingEntry:
        return AccountingEntry.model_validate(extracted_model.model_dump(mode="python"))


def get_workflow() -> InvoiceAutopostingWorkflow:
    return InvoiceAutopostingWorkflow()
