from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.runtime.observability import ObservabilityService
from core.runtime.engine import LangChainWorkflowEngine
from core.workflows.base import BaseWorkflow


class EvalCase(BaseModel):
    document_id: str
    workflow: str
    source_text: str
    expected_fields: dict[str, Any]


class EvalCaseResult(BaseModel):
    document_id: str
    matched_fields: dict[str, bool]
    extracted_data: dict[str, Any]
    score: float


class EvaluationReport(BaseModel):
    workflow_name: str
    mode: str
    total_cases: int
    passed_cases: int
    field_accuracy: float
    cases: list[EvalCaseResult] = Field(default_factory=list)


class EvaluationService:
    def __init__(
        self,
        eval_sets_root: Path,
        engine: LangChainWorkflowEngine,
        observability: ObservabilityService,
    ) -> None:
        self.eval_sets_root = eval_sets_root
        self.engine = engine
        self.observability = observability

    async def run_workflow_eval(self, workflow: BaseWorkflow, mode: str = "fallback") -> EvaluationReport:
        cases = self._load_cases(workflow.metadata.name)
        case_results: list[EvalCaseResult] = []

        for case in cases:
            extracted_model = await self._extract_case(workflow, case, mode=mode)
            extracted_data = extracted_model.model_dump(mode="json")
            matched_fields = {
                key: self._values_match(expected_value, extracted_data.get(key))
                for key, expected_value in case.expected_fields.items()
            }
            score = sum(1 for matched in matched_fields.values() if matched) / len(matched_fields)
            case_results.append(
                EvalCaseResult(
                    document_id=case.document_id,
                    matched_fields=matched_fields,
                    extracted_data=extracted_data,
                    score=score,
                )
            )

        passed_cases = sum(1 for result in case_results if result.score == 1.0)
        field_accuracy = (
            sum(result.score for result in case_results) / len(case_results)
            if case_results
            else 0.0
        )
        report = EvaluationReport(
            workflow_name=workflow.metadata.name,
            mode=mode,
            total_cases=len(case_results),
            passed_cases=passed_cases,
            field_accuracy=field_accuracy,
            cases=case_results,
        )
        self.observability.record_evaluation(
            workflow_name=workflow.metadata.name,
            run_name=f"{workflow.metadata.name}_{mode}_eval",
            payload={"total_cases": report.total_cases, "mode": mode},
            metrics={"field_accuracy": field_accuracy, "passed_cases": float(passed_cases)},
        )
        return report

    def _load_cases(self, workflow_name: str) -> list[EvalCase]:
        direct_path = self.eval_sets_root / f"{workflow_name}_eval.json"
        fallback_path = self.eval_sets_root / f"{workflow_name.split('_')[0]}_eval.json"
        eval_path = direct_path if direct_path.exists() else fallback_path
        raw_cases = json.loads(eval_path.read_text(encoding="utf-8"))
        return [EvalCase.model_validate(case) for case in raw_cases]

    async def _extract_case(self, workflow: BaseWorkflow, case: EvalCase, mode: str):
        if mode not in {"fallback", "llm", "auto"}:
            raise ValueError(f"Unsupported evaluation mode '{mode}'.")

        if mode == "fallback":
            return workflow.fallback_extract(case.source_text)

        if mode == "llm":
            return await self.engine.extract_structured(
                workflow_name=workflow.metadata.name,
                system_prompt=workflow.extraction_system_prompt(),
                document_text=case.source_text,
                output_model=workflow.output_schema_model(),
            )

        if self.engine.is_ready():
            try:
                return await self.engine.extract_structured(
                    workflow_name=workflow.metadata.name,
                    system_prompt=workflow.extraction_system_prompt(),
                    document_text=case.source_text,
                    output_model=workflow.output_schema_model(),
                )
            except Exception:
                pass

        return workflow.fallback_extract(case.source_text)

    @staticmethod
    def _values_match(expected: Any, actual: Any) -> bool:
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except (InvalidOperation, TypeError, ValueError):
            return expected == actual
