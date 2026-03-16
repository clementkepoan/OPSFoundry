from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from core.domain.work_items import WorkItem


class AuditEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    workflow_name: str
    work_item_id: str | None = None
    actor: str = "system"
    payload: dict[str, Any] = Field(default_factory=dict)


class AuditService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def record(
        self,
        event_type: str,
        workflow_name: str,
        work_item: WorkItem | None = None,
        payload: dict[str, Any] | None = None,
        actor: str = "system",
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            workflow_name=workflow_name,
            work_item_id=work_item.id if work_item else None,
            actor=actor,
            payload=payload or {},
        )
        return self.repository.append(event)

    def list_events(self, work_item_id: str | None = None) -> list[AuditEvent]:
        return self.repository.list(work_item_id=work_item_id)
