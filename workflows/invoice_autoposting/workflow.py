from pathlib import Path

import yaml

from core.workflow_registry.base import BaseWorkflow, WorkflowMetadata

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

    @staticmethod
    def _load_config() -> dict[str, object]:
        with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)

        config["name"] = config.pop("workflow_name")
        return config


def get_workflow() -> InvoiceAutopostingWorkflow:
    return InvoiceAutopostingWorkflow()
