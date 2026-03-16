import json
from pathlib import Path

from core.domain.work_items import WorkItem


class FileWorkItemRepository:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save(self, work_item: WorkItem) -> WorkItem:
        item_path = self.root_dir / f"{work_item.id}.json"
        item_path.write_text(
            json.dumps(work_item.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        return work_item

    def get(self, work_item_id: str) -> WorkItem:
        item_path = self.root_dir / f"{work_item_id}.json"
        if not item_path.exists():
            raise KeyError(f"Unknown work item '{work_item_id}'")

        return WorkItem.model_validate_json(item_path.read_text(encoding="utf-8"))

    def list(self, workflow_name: str | None = None) -> list[WorkItem]:
        items = [
            WorkItem.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self.root_dir.glob("*.json")
        ]
        if workflow_name is not None:
            items = [item for item in items if item.workflow_name == workflow_name]

        return sorted(items, key=lambda item: item.created_at, reverse=True)
