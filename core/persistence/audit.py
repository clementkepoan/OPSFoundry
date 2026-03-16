from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.runtime.audit import AuditEvent
from core.persistence.models import AuditEventRecord


class SQLAuditRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def append(self, event: AuditEvent) -> AuditEvent:
        with self.session_factory() as session:
            session.add(
                AuditEventRecord(
                    timestamp=event.timestamp,
                    event_type=event.event_type,
                    workflow_name=event.workflow_name,
                    work_item_id=event.work_item_id,
                    actor=event.actor,
                    payload=event.payload,
                )
            )
            session.commit()
        return event

    def list(self, work_item_id: str | None = None) -> list[AuditEvent]:
        with self.session_factory() as session:
            statement = select(AuditEventRecord).order_by(AuditEventRecord.timestamp.asc(), AuditEventRecord.id.asc())
            if work_item_id is not None:
                statement = statement.where(AuditEventRecord.work_item_id == work_item_id)
            records = session.scalars(statement).all()
            return [
                AuditEvent(
                    timestamp=record.timestamp,
                    event_type=record.event_type,
                    workflow_name=record.workflow_name,
                    work_item_id=record.work_item_id,
                    actor=record.actor,
                    payload=record.payload,
                )
                for record in records
            ]
