from abc import ABC, abstractmethod
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class TrackingRecord(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    category: str
    workflow_name: str
    run_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)


class BaseTracker(ABC):
    backend_name: str

    @abstractmethod
    def log_event(self, record: TrackingRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def log_evaluation(self, record: TrackingRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> dict[str, Any]:
        raise NotImplementedError


class FileTracker(BaseTracker):
    backend_name = "file"

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.root_dir / "tracking.jsonl"

    def log_event(self, record: TrackingRecord) -> None:
        self._append(record)

    def log_evaluation(self, record: TrackingRecord) -> None:
        self._append(record)

    def status(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "path": str(self.path),
        }

    def _append(self, record: TrackingRecord) -> None:
        with self.path.open("a", encoding="utf-8") as tracking_file:
            tracking_file.write(json.dumps(record.model_dump(mode="json")) + "\n")


class MLflowTracker(BaseTracker):
    backend_name = "mlflow"

    def __init__(self, tracking_uri: str, experiment_name: str) -> None:
        self.tracking_uri = tracking_uri
        self.experiment_name = experiment_name

    def log_event(self, record: TrackingRecord) -> None:
        mlflow = self._mlflow()
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(self.experiment_name)
        with mlflow.start_run(run_name=record.run_name):
            mlflow.set_tags(
                {
                    "category": record.category,
                    "workflow_name": record.workflow_name,
                }
            )
            for key, value in record.payload.items():
                mlflow.log_param(key, self._stringify(value))

    def log_evaluation(self, record: TrackingRecord) -> None:
        mlflow = self._mlflow()
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(self.experiment_name)
        with mlflow.start_run(run_name=record.run_name):
            mlflow.set_tags(
                {
                    "category": record.category,
                    "workflow_name": record.workflow_name,
                }
            )
            for key, value in record.payload.items():
                mlflow.log_param(key, self._stringify(value))
            for key, value in record.metrics.items():
                mlflow.log_metric(key, value)

    def status(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "tracking_uri": self.tracking_uri,
            "experiment_name": self.experiment_name,
        }

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return str(value)

    @staticmethod
    def _mlflow():
        import mlflow

        return mlflow
