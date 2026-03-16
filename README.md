# OPSFoundry

OPSFoundry is a modular workflow automation platform. The current implemented workflow is `invoice_autoposting`, with reusable core services for intake, OCR, extraction, validation, review, export, and observability.

## Current Stack

- API: FastAPI (`apps/api`)
- Frontend: Next.js (`apps/frontend`)
- OCR: Google Cloud Vision API (plus plain-text passthrough for `text/*`)
- LLM extraction: DeepSeek (with deterministic fallback parser)
- Persistence: Postgres for work items/audit, Redis for duplicate-request guard
- Artifacts: local file storage under `storage/` (documents, exports, MLflow runs)
- Tracking: MLflow UI

## Quick Start

1. Copy environment file:
```bash
cp .env.example .env
```
2. Configure OCR credentials (see `OCR Setup` below).
3. Start everything:
```bash
docker compose up --build
```
4. Open:
- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- MLflow: `http://localhost:5055`

## Main API Flow (Invoice)

- Upload (auto-runs extraction):
```bash
curl -X POST http://localhost:8000/api/v1/workflows/invoice_autoposting/documents \
  -F "file=@sample.png;type=image/png"
```
- Validate (auto-exports CSV when validation passes):
```bash
curl -X POST http://localhost:8000/api/v1/work-items/<work_item_id>/validate
```
- Review queue + decision for failed validation:
```bash
curl http://localhost:8000/api/v1/review-queue
curl -X POST http://localhost:8000/api/v1/work-items/<work_item_id>/review \
  -H "Content-Type: application/json" \
  -d '{"action":"approve","review_notes":"manual review complete"}'
```

## Development and Tests

- Run tests locally:
```bash
pytest -q
```
- Run tests inside Docker API container:
```bash
docker compose run --rm api pytest -q
```

## Repository Layout

```text
apps/                 # API + Next.js frontend
core/                 # shared domain, runtime, workflows, persistence, documents
workflows/            # workflow configs (invoice_autoposting)
mlops/eval_sets/      # evaluation datasets
mcp_servers/          # optional MCP integrations
tests/                # backend tests
storage/              # local runtime artifacts
```

## OCR Setup Note

1. Put your GCP service-account key JSON under `secrets/` (any filename is fine).
2. Set `.env` to the in-container path that matches your filename:
```bash
GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/<your-key-file>.json
OCR_PDF_MAX_PAGES=5
```
`docker-compose.yml` mounts `./secrets` into `/app/secrets` (read-only) for the API service.

## Database Configuration

- In Docker Compose, `DATABASE_URL` is optional. The app automatically builds it from:
  `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`.
- If you prefer explicit config, use:
```bash
DATABASE_URL=postgresql+psycopg://opsfoundry:opsfoundry@postgres:5432/opsfoundry
```
- Inside containers, use host `postgres` (service name), not `localhost`.
