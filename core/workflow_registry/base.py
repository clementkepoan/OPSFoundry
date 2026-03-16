from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    root_dir: Path


class BaseWorkflow(ABC):
    @property
    @abstractmethod
    def metadata(self) -> WorkflowMetadata:
        raise NotImplementedError

    @abstractmethod
    def step_pipeline(self) -> list[str]:
        raise NotImplementedError

    def bootstrap_payload(self) -> dict[str, Any]:
        return {
            "workflow_name": self.metadata.name,
            "step_pipeline": self.step_pipeline(),
            "supported_states": self.metadata.states,
        }
