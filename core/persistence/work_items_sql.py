from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.persistence.models import WorkItemRecord
from core.domain.work_items import WorkItem


class SQLWorkItemRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def save(self, work_item: WorkItem) -> WorkItem:
        with self.session_factory() as session:
            record = session.get(WorkItemRecord, work_item.id)
            payload = work_item.model_dump(mode="json")
            if record is None:
                record = WorkItemRecord(
                    id=work_item.id,
                    workflow_name=work_item.workflow_name,
                    state=work_item.state,
                    created_at=work_item.created_at,
                    updated_at=work_item.updated_at,
                    payload=payload,
                )
                session.add(record)
            else:
                record.workflow_name = work_item.workflow_name
                record.state = work_item.state
                record.created_at = work_item.created_at
                record.updated_at = work_item.updated_at
                record.payload = payload
            session.commit()
        return work_item

    def get(self, work_item_id: str) -> WorkItem:
        with self.session_factory() as session:
            record = session.get(WorkItemRecord, work_item_id)
            if record is None:
                raise KeyError(f"Unknown work item '{work_item_id}'")
            return WorkItem.model_validate(record.payload)

    def list(self, workflow_name: str | None = None) -> list[WorkItem]:
        with self.session_factory() as session:
            statement = select(WorkItemRecord).order_by(WorkItemRecord.created_at.desc())
            if workflow_name is not None:
                statement = statement.where(WorkItemRecord.workflow_name == workflow_name)
            records = session.scalars(statement).all()
            return [WorkItem.model_validate(record.payload) for record in records]
