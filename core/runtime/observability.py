from typing import Any

from core.runtime.audit import AuditEvent, AuditService
from core.config.settings import Settings
from core.runtime.tracker import BaseTracker, FileTracker, MLflowTracker, TrackingRecord
from core.domain.work_items import WorkItem


class ObservabilityService:
    def __init__(self, settings: Settings, audit_service: AuditService) -> None:
        self.settings = settings
        self.audit_service = audit_service
        self.tracker = self._build_tracker()

    def record_workflow_event(
        self,
        event_type: str,
        workflow_name: str,
        work_item: WorkItem | None = None,
        payload: dict[str, Any] | None = None,
        actor: str = "system",
    ) -> AuditEvent:
        audit_event = self.audit_service.record(
            event_type=event_type,
            workflow_name=workflow_name,
            work_item=work_item,
            payload=payload,
            actor=actor,
        )
        record = TrackingRecord(
            category="workflow_event",
            workflow_name=workflow_name,
            run_name=event_type,
            payload={
                "work_item_id": work_item.id if work_item else None,
                **(payload or {}),
            },
        )
        self.tracker.log_event(record)
        return audit_event

    def record_evaluation(
        self,
        workflow_name: str,
        run_name: str,
        payload: dict[str, Any],
        metrics: dict[str, float],
    ) -> None:
        record = TrackingRecord(
            category="evaluation",
            workflow_name=workflow_name,
            run_name=run_name,
            payload=payload,
            metrics=metrics,
        )
        self.tracker.log_evaluation(record)

    def audit_events(self, work_item_id: str | None = None) -> list[AuditEvent]:
        return self.audit_service.list_events(work_item_id=work_item_id)

    def status(self) -> dict[str, Any]:
        tracker_status = self.tracker.status()
        tracker_status["audit_backend"] = type(self.audit_service.repository).__name__
        return tracker_status

    def _build_tracker(self) -> BaseTracker:
        tracking_uri = self.settings.mlflow_tracking_uri or f"file://{self.settings.mlflow_storage_dir.resolve()}"
        try:
            __import__("mlflow")
            return MLflowTracker(
                tracking_uri=tracking_uri,
                experiment_name=self.settings.mlflow_experiment_name,
            )
        except ImportError:
            return FileTracker(self.settings.mlflow_storage_dir)
