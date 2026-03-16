from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from core.config.settings import Settings
from core.documents.ocr import OCRResult, OCRService


def test_create_app_fails_when_ocr_warmup_is_strict_and_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_warmup(self) -> OCRResult:
        return OCRResult(
            backend="google_vision",
            status="backend_unavailable",
            warnings=["simulated warmup failure"],
        )

    monkeypatch.setattr(OCRService, "warmup", fake_warmup)
    settings = Settings(
        storage_root=tmp_path / "storage",
        database_url=f"sqlite+pysqlite:///{tmp_path / 'strict-startup.db'}",
        ocr_warmup_on_startup=True,
        ocr_warmup_strict=True,
    )

    with pytest.raises(RuntimeError, match="simulated warmup failure"):
        create_app(settings)


def test_create_app_allows_ocr_warmup_failure_when_not_strict(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_warmup(self) -> OCRResult:
        return OCRResult(
            backend="google_vision",
            status="backend_unavailable",
            warnings=["simulated warmup failure"],
        )

    monkeypatch.setattr(OCRService, "warmup", fake_warmup)
    settings = Settings(
        storage_root=tmp_path / "storage",
        database_url=f"sqlite+pysqlite:///{tmp_path / 'non-strict-startup.db'}",
        ocr_warmup_on_startup=True,
        ocr_warmup_strict=False,
    )

    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
