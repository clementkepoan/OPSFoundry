# Repository Guidelines

## Project Structure & Module Organization

OPSFoundry is a Python workflow platform. The FastAPI entrypoint is `apps/api/main.py`. Generic runtime code lives in `core/`: orchestration in `core/orchestration/`, workflow contracts in `core/workflow_registry/`, DB infrastructure in `core/database/`, validation/review/export/audit services in their matching `core/*` packages, and document storage in `core/storage/`. Workflow-specific logic must stay under `workflows/<workflow_name>/`; `workflows/invoice_autoposting/` is the reference layout. MCP stubs live in `mcp_servers/`, eval fixtures in `mlops/eval_sets/`, runtime file artifacts in `storage/`, and tests in `tests/`.

## Build, Test, and Development Commands

- `make install`: install the app in editable mode with dev dependencies.
- `make run`: start the API locally with reload on port `8000`.
- `make up`: start the Docker stack (`api`, `postgres`, `redis`, `mlflow`).
- `make down`: stop the Docker stack.
- `make test`: run `pytest`.
- `make lint`: run `ruff check .`.

Typical setup:

```bash
cp .env.example .env
make install
make test
docker compose up --build
```

## Coding Style & Naming Conventions

Use Python 3.11+ with 4-space indentation, explicit type hints, and small Pydantic models. Keep the API and generic `core/` services workflow-agnostic. Put invoice- or workflow-specific parsing, prompts, validators, and export mapping inside `workflows/`. Use `snake_case` for modules/functions and `PascalCase` for classes. Prefer deterministic fallbacks and explicit state transitions over hidden side effects.

## Testing Guidelines

Tests use `pytest`; files should be named `test_<area>.py` and functions `test_<behavior>()`. The test fixture uses a temporary SQLite database even though production targets Postgres, so new persistence changes should remain dialect-safe. Add tests for route behavior, workflow contracts, validation/review state transitions, exports, and eval runs.

## Commit & Pull Request Guidelines

Follow the existing short imperative commit style, for example `Initial Scaffold`. Keep subjects capitalized and concise. PRs should include a short summary, affected paths, verification steps, and screenshots only for UI changes.

## Security & Configuration Tips

Never commit `.env` or live API keys. `DATABASE_URL` can override the default Postgres DSN. Work item state and audit events are DB-backed; raw documents, exports, and MLflow artifacts remain under `storage/`.
