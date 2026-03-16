import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config.settings import Settings

os.environ.setdefault("OCR_WARMUP_ON_STARTUP", "false")
os.environ.setdefault("OCR_WARMUP_STRICT", "false")

from apps.api.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    storage_root = tmp_path / "storage"
    database_path = tmp_path / "opsfoundry-test.db"
    settings = Settings(
        storage_root=storage_root,
        database_url=f"sqlite+pysqlite:///{database_path}",
        ocr_warmup_on_startup=False,
        ocr_warmup_strict=False,
    )
    return TestClient(create_app(settings))
