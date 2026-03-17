from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.workflows.validation_models import AnomalyFlag, ValidationResult


class WorkflowMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    version: str = "0.1.0"
    states: list[str] = Field(default_factory=list)
    input_schema: str
    output_schema: str
    tools: list[str] = Field(default_factory=list)
    validators: list[str] = Field(default_factory=list)
    exports: list[str] = Field(default_factory=list)
    invoice_categories: list[str] = Field(default_factory=list)
    extractable_fields: list[str] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=list)
    default_target_currency: str = "USD"
    root_dir: Path


class BaseWorkflow(ABC):
    @property
    @abstractmethod
    def metadata(self) -> WorkflowMetadata:
        raise NotImplementedError

    @abstractmethod
    def step_pipeline(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def output_schema_model(self) -> type[BaseModel]:
        raise NotImplementedError

    @abstractmethod
    def extraction_system_prompt(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def fallback_extract(self, document_text: str) -> BaseModel:
        raise NotImplementedError

    @abstractmethod
    def validate_extracted_payload(self, extracted_model: BaseModel) -> list[ValidationResult]:
        raise NotImplementedError

    @abstractmethod
    def detect_anomalies(
        self,
        extracted_model: BaseModel,
        validation_results: list[ValidationResult],
    ) -> list[AnomalyFlag]:
        raise NotImplementedError

    @abstractmethod
    def export_rows(self, extracted_model: BaseModel) -> list[dict[str, Any]]:
        raise NotImplementedError

    def bootstrap_payload(self) -> dict[str, Any]:
        return {
            "workflow_name": self.metadata.name,
            "step_pipeline": self.step_pipeline(),
            "supported_states": self.metadata.states,
        }
