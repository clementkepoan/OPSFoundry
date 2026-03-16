from functools import lru_cache
from importlib import import_module
from pathlib import Path

from core.workflows.base import BaseWorkflow

WORKFLOWS_ROOT = Path(__file__).resolve().parents[2] / "workflows"


class WorkflowRegistry:
    def __init__(self, workflows_root: Path = WORKFLOWS_ROOT) -> None:
        self.workflows_root = workflows_root
        self._workflows: dict[str, BaseWorkflow] = {}

    def discover(self) -> "WorkflowRegistry":
        for workflow_file in sorted(self.workflows_root.glob("*/workflow.py")):
            workflow_name = workflow_file.parent.name
            module = import_module(f"workflows.{workflow_name}.workflow")
            factory = getattr(module, "get_workflow", None)
            if not callable(factory):
                raise TypeError(
                    f"Workflow module 'workflows.{workflow_name}.workflow' must define get_workflow()."
                )

            self.register(factory())

        return self

    def register(self, workflow: BaseWorkflow) -> None:
        name = workflow.metadata.name
        if name in self._workflows:
            raise ValueError(f"Workflow '{name}' is already registered.")

        self._workflows[name] = workflow

    def get(self, workflow_name: str) -> BaseWorkflow:
        return self._workflows[workflow_name]

    def all(self) -> list[BaseWorkflow]:
        return [self._workflows[name] for name in sorted(self._workflows)]

    def names(self) -> list[str]:
        return sorted(self._workflows)


@lru_cache(maxsize=1)
def get_registry() -> WorkflowRegistry:
    return WorkflowRegistry().discover()
