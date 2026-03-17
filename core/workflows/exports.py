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
        extracted_payload = work_item.metadata.get("canonical_extracted_data")
        if not isinstance(extracted_payload, dict):
            extracted_payload = work_item.extracted_data

        if not extracted_payload:
            raise ValueError("Work item does not contain extracted data.")
        if export_format not in workflow.metadata.exports:
            raise ValueError(f"Export format '{export_format}' is not supported.")

        extracted_model = workflow.output_schema_model().model_validate(extracted_payload)
        workflow_dir = self.root_dir / workflow.metadata.name
        workflow_dir.mkdir(parents=True, exist_ok=True)
        safe_category = self._sanitize_category(work_item.category)

        if export_format == "csv":
            filename = self.workflow_csv_filename(workflow.metadata.name, safe_category)
            path = workflow_dir / filename
            rows = workflow.export_rows(extracted_model)
            if not rows:
                raise ValueError("Workflow export produced no rows.")
            rows = self._filter_rows_by_selected_fields(
                rows=rows,
                selected_fields=work_item.metadata.get("extraction_settings", {}).get("selected_fields"),
            )
            exported_at = datetime.now(UTC).isoformat()
            enriched_rows = [
                {
                    "category": safe_category,
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

    def workflow_csv_path(self, workflow_name: str, category: str = "uncategorized") -> Path:
        safe_category = self._sanitize_category(category)
        return self.root_dir / workflow_name / self.workflow_csv_filename(workflow_name, safe_category)

    def remove_work_item_from_category_csv(
        self,
        workflow_name: str,
        category: str,
        work_item_id: str,
    ) -> int:
        path = self.workflow_csv_path(workflow_name, category=category)
        if not path.exists():
            return 0

        with path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            fieldnames = reader.fieldnames or []
            rows = list(reader)

        kept_rows = [row for row in rows if row.get("work_item_id") != work_item_id]
        removed_count = len(rows) - len(kept_rows)
        if removed_count == 0:
            return 0

        if not kept_rows:
            path.unlink(missing_ok=True)
            return removed_count

        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(kept_rows)
        return removed_count

    @staticmethod
    def workflow_csv_filename(workflow_name: str, category: str) -> str:
        return f"{workflow_name}_{category}_portfolio.csv"

    @staticmethod
    def _sanitize_category(category: str) -> str:
        cleaned = "".join(
            char if char.isalnum() or char in {"-", "_"} else "_"
            for char in category.strip().lower()
        )
        return cleaned or "uncategorized"

    @staticmethod
    def _filter_rows_by_selected_fields(
        rows: list[dict[str, object]],
        selected_fields: object,
    ) -> list[dict[str, object]]:
        if not isinstance(selected_fields, list) or not selected_fields:
            return rows

        selected = {field for field in selected_fields if isinstance(field, str)}
        field_map = {
            "vendor_name": {"vendor_name"},
            "invoice_number": {"invoice_number"},
            "invoice_date": {"invoice_date"},
            "currency": {"currency"},
            "subtotal": {"subtotal"},
            "tax_amount": {"tax_amount"},
            "total_amount": {"total_amount"},
            "payment_terms": {"payment_terms"},
            "line_items": {
                "line_description",
                "quantity",
                "unit_price",
                "amount",
                "line_subtotal",
                "account_code",
                "cost_center",
            },
        }
        allowed_columns = {
            "category",
            "work_item_id",
            "source_filename",
            "exported_at",
        }
        for field in selected:
            allowed_columns.update(field_map.get(field, set()))

        filtered_rows: list[dict[str, object]] = []
        for row in rows:
            filtered_rows.append({key: value for key, value in row.items() if key in allowed_columns})
        return filtered_rows
