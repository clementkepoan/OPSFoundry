from typing import Any

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    name: str
    passed: bool
    message: str | None = None
    details: dict[str, str] = Field(default_factory=dict)


class AnomalyFlag(BaseModel):
    code: str
    severity: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationRun(BaseModel):
    status: str
    results: list[ValidationResult] = Field(default_factory=list)
    anomalies: list[AnomalyFlag] = Field(default_factory=list)
