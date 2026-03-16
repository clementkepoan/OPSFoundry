from datetime import UTC, datetime
import csv
import json
from pathlib import Path

from pydantic import BaseModel

from core.domain.work_items import WorkItem
from core.workflows.base import BaseWorkflow


class ExportArtifact(BaseModel):
    format: str
    path: str
    filename: str


class ExportService:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def export_work_item(
        self,
        workflow: BaseWorkflow,
        work_item: WorkItem,
        export_format: str = "csv",
    ) -> tuple[WorkItem, ExportArtifact]:
        if work_item.state not in {"validated", "approved", "exported"}:
            raise ValueError("Only validated or approved work items can be exported.")
        if not work_item.extracted_data:
            raise ValueError("Work item does not contain extracted data.")
        if export_format not in workflow.metadata.exports:
            raise ValueError(f"Export format '{export_format}' is not supported.")

        extracted_model = workflow.output_schema_model().model_validate(work_item.extracted_data)
        workflow_dir = self.root_dir / workflow.metadata.name
        workflow_dir.mkdir(parents=True, exist_ok=True)

        if export_format == "csv":
            filename = self.workflow_csv_filename(workflow.metadata.name)
            path = workflow_dir / filename
            rows = workflow.export_rows(extracted_model)
            if not rows:
                raise ValueError("Workflow export produced no rows.")
            exported_at = datetime.now(UTC).isoformat()
            enriched_rows = [
                {
                    "work_item_id": work_item.id,
                    "source_filename": work_item.filename,
                    "exported_at": exported_at,
                    **row,
                }
                for row in rows
            ]
            fieldnames = list(enriched_rows[0].keys())
            file_exists = path.exists() and path.stat().st_size > 0
            with path.open("a", encoding="utf-8", newline="") as export_file:
                writer = csv.DictWriter(export_file, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(enriched_rows)
        elif export_format == "json":
            filename = f"{work_item.id}.json"
            path = workflow_dir / filename
            path.write_text(
                json.dumps(extracted_model.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )
        else:
            raise ValueError(f"Unsupported export format '{export_format}'.")

        artifact = ExportArtifact(
            format=export_format,
            path=str(path),
            filename=filename,
        )
        history = list(work_item.export_history)
        history.append(artifact.model_dump(mode="json"))
        updated_item = work_item.model_copy(
            update={
                "state": "exported",
                "export_status": "completed",
                "exported_artifact": artifact.model_dump(mode="json"),
                "export_history": history,
                "updated_at": datetime.now(UTC),
            }
        )
        return updated_item, artifact

    def workflow_csv_path(self, workflow_name: str) -> Path:
        return self.root_dir / workflow_name / self.workflow_csv_filename(workflow_name)

    @staticmethod
    def workflow_csv_filename(workflow_name: str) -> str:
        return f"{workflow_name}_portfolio.csv"
