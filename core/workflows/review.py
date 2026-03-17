from datetime import UTC, datetime
from typing import Any

from core.domain.work_items import WorkItem
from core.workflows.base import BaseWorkflow


class ReviewService:
    def list_queue(self, work_items: list[WorkItem], workflow_name: str | None = None) -> list[WorkItem]:
        queue = [
            item
            for item in work_items
            if item.review_status in {"queued", "in_review"} or item.state == "needs_review"
        ]
        if workflow_name is not None:
            queue = [item for item in queue if item.workflow_name == workflow_name]
        return sorted(queue, key=lambda item: item.updated_at, reverse=True)

    def apply_review_action(
        self,
        workflow: BaseWorkflow,
        work_item: WorkItem,
        action: str,
        review_notes: str | None = None,
        updated_data: dict[str, Any] | None = None,
    ) -> WorkItem:
        if action not in {"approve", "reject"}:
            raise ValueError(f"Unsupported review action '{action}'.")
        if work_item.review_status not in {"queued", "in_review"} and work_item.state != "needs_review":
            raise ValueError("Only work items in the review queue can be approved or rejected.")

        extracted_data = work_item.extracted_data
        metadata = dict(work_item.metadata)
        canonical_data = metadata.get("canonical_extracted_data")
        if not isinstance(canonical_data, dict):
            canonical_data = extracted_data if isinstance(extracted_data, dict) else {}

        if updated_data is not None:
            merged_payload = {
                **canonical_data,
                **updated_data,
            }
            extracted_model = workflow.output_schema_model().model_validate(merged_payload)
            canonical_data = extracted_model.model_dump(mode="json")
            selected_fields = metadata.get("extraction_settings", {}).get("selected_fields")
            extracted_data = _filter_payload(canonical_data, selected_fields)
            metadata["canonical_extracted_data"] = canonical_data

        if action == "approve":
            next_state = "approved"
            review_status = "approved"
        else:
            next_state = "rejected"
            review_status = "rejected"

        review_history = list(work_item.review_history)
        review_history.append(
            {
                "action": action,
                "notes": review_notes,
                "updated_data_applied": updated_data is not None,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        return work_item.model_copy(
            update={
                "state": next_state,
                "review_status": review_status,
                "review_notes": review_notes,
                "review_history": review_history,
                "extracted_data": extracted_data,
                "metadata": metadata,
                "updated_at": datetime.now(UTC),
            }
        )


def _filter_payload(payload: dict[str, Any], selected_fields: object) -> dict[str, Any]:
    if not isinstance(selected_fields, list) or not selected_fields:
        return payload
    allowed = {field for field in selected_fields if isinstance(field, str)}
    if payload.get("explanation") is not None:
        allowed.add("explanation")
    return {key: value for key, value in payload.items() if key in allowed}
