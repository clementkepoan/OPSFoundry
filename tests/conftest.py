from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from core.config.settings import Settings


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    storage_root = tmp_path / "storage"
    database_path = tmp_path / "opsfoundry-test.db"
    settings = Settings(
        storage_root=storage_root,
        database_url=f"sqlite+pysqlite:///{database_path}",
    )
    return TestClient(create_app(settings))
