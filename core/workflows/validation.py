from datetime import UTC, datetime

from pydantic import BaseModel

from core.workflows.validation_models import AnomalyFlag, ValidationRun, ValidationResult
from core.domain.work_items import WorkItem
from core.workflows.base import BaseWorkflow


class ValidationService:
    def validate_work_item(self, workflow: BaseWorkflow, work_item: WorkItem) -> tuple[WorkItem, ValidationRun]:
        extracted_payload = work_item.metadata.get("canonical_extracted_data")
        if not isinstance(extracted_payload, dict):
            extracted_payload = work_item.extracted_data

        if not extracted_payload:
            run = ValidationRun(status="failed")
            updated_item = work_item.model_copy(
                update={
                    "validation_status": "failed",
                    "validation_results": [],
                    "anomaly_flags": [],
                    "state": work_item.state,
                    "updated_at": datetime.now(UTC),
                }
            )
            return updated_item, run

        extracted_model = workflow.output_schema_model().model_validate(extracted_payload)
        validation_results = workflow.validate_extracted_payload(extracted_model)
        anomalies = workflow.detect_anomalies(extracted_model, validation_results)

        passed = all(result.passed for result in validation_results)
        needs_review = (not passed) or any(flag.severity in {"medium", "high", "critical"} for flag in anomalies)
        next_state = "needs_review" if needs_review else "validated"
        review_status = "queued" if needs_review else "not_required"

        updated_item = work_item.model_copy(
            update={
                "state": next_state,
                "validation_status": "needs_review" if needs_review else "passed",
                "validation_results": [result.model_dump(mode="json") for result in validation_results],
                "anomaly_flags": [flag.model_dump(mode="json") for flag in anomalies],
                "review_status": review_status,
                "updated_at": datetime.now(UTC),
            }
        )
        run = ValidationRun(
            status="needs_review" if needs_review else "passed",
            results=validation_results,
            anomalies=anomalies,
        )
        return updated_item, run
