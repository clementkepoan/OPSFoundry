# Session 1 Summary

## Date
- March 16, 2026

## Objective
- Continue building OPSFoundry by following `mainplan.md`
- Ship the backend workflow from intake through export
- Add a frontend UI
- Improve workflow routing behavior
- Start making the codebase easier to scale for multiple workflows

## Major Work Completed

### 1. Day 1 Platform Scaffold
- Added initial backend project setup with FastAPI, Docker, environment scaffolding, and Python dependencies.
- Added workflow registry and plugin structure so workflows can live under `workflows/` instead of being hardcoded into the API.
- Added the initial `invoice_autoposting` workflow package with schemas, prompts, validators, and workflow metadata.
- Added basic README and `.env.example`.
- Added initial MCP placeholder server under `mcp_servers/coa_tool/server.py`.
- Added initial evaluation dataset under `mlops/eval_sets/invoice_eval.json`.

### 2. Day 2 Intake Flow
- Implemented upload intake for workflow documents.
- Added local object storage for uploaded files and metadata under `storage/`.
- Added work item creation and persistence.
- Added OCR abstraction and document download endpoints.
- Added API endpoints for:
  - document upload
  - work item listing
  - work item detail
  - document metadata
  - document download

### 3. Day 2 Findings Fixes
- Fixed intake atomicity so failed persistence does not leave orphaned files.
- Fixed download behavior so missing stored files return `404`.
- Reduced wasteful upload handling by avoiding an unnecessary full-memory read before storage.
- Added tests for rollback and missing-file handling.

### 4. Day 2.5 Real OCR
- Replaced the placeholder OCR-only path with real Tesseract support for image and PDF OCR.
- Updated Docker to install OCR dependencies.
- Preserved plain-text direct extraction for `.txt` and similar text-native files.
- Verified that image uploads used `ocr_backend: "tesseract"` and completed extraction successfully.

### 5. Day 3 Structured Extraction
- Added structured extraction service on top of OCR text.
- Integrated DeepSeek through the LangChain runtime.
- Added deterministic fallback extraction when DeepSeek is unavailable.
- Persisted OCR text and extracted structured payload on work items.
- Added `/extract` API route.

### 6. Day 4 and Day 5 Validation, Review, Export, Audit
- Added validation service and anomaly detection.
- Added review queue logic and approve/reject actions.
- Added CSV and JSON export support.
- Added audit logging for document upload, extraction, validation, review, and export events.
- Added API routes for:
  - `/validate`
  - `/review-queue`
  - `/review`
  - `/export`
  - `/audit`

### 7. Behavior Redesign Requested by User
- Changed the workflow to match the desired operational routing:
  - `Upload -> Extract`
  - `Validate`
  - if clean: auto-export
  - if not clean: queue for review
  - review queue items can be approved or rejected
  - approval auto-exports
- Review is no longer meant as a generic step for every item.
- Validation became the real branching point.

### 8. Validation Bug Fix
- Added a validator so invoices with:
  - `subtotal = 0`
  - `tax_amount = 0`
  - `total_amount = 0`
  do not pass as valid.
- Implemented `meaningful_amounts` in `workflows/invoice_autoposting/validators.py`.
- Added regression coverage for the zero-amount scenario.

### 9. Review Rule Tightening
- Restricted approve/reject actions so they only apply to items actually in the review queue.
- Prevented already clean / already exported items from being “reviewed” incorrectly.

### 10. Upload Auto-Extraction
- Updated document upload so it now triggers extraction immediately after intake.
- Upload responses now return:
  - document metadata
  - OCR result
  - updated extracted work item
  - extraction result
- This removed one more manual operational step from the user flow.

## Frontend Work

### 11. Initial Next.js Frontend
- Added a Next.js frontend under `apps/frontend`.
- Wired the frontend to existing API routes.
- Added CORS support in the backend.
- Added a frontend Docker service.

### 12. Frontend Redesign
- Replaced the first dashboard with a more intentional dark operations console.
- Reworked the UI around the actual workflow behavior instead of exposing too many manual actions.
- Added:
  - hero/status area
  - metrics cards
  - review queue panel
  - work item ledger
  - detail panel
  - stage progression
  - audit timeline
  - observability panel

### 13. Workflow Selection UX
- Added a workflow selection landing page at `/`.
- Added redirect into a workflow-specific HUD at `/workflows/[workflowName]`.
- Scoped the HUD to the chosen workflow by filtering:
  - work item list
  - review queue
  - workflow metadata display
- Updated upload UI so the workflow is selected before entering the HUD.

## Observability / ML / MLflow
- Added observability service and tracking layer.
- Added MLflow support with fallback file tracking.
- Added evaluation runner and observability status endpoint.
- Changed MLflow host port from `5000` to `5055`.
- Clarified that:
  - Tesseract performs OCR
  - DeepSeek performs extraction
  - MLflow tracks runs and evaluation metadata
  - MLflow is not doing inference itself

## Docker / Runtime Notes
- Docker Compose currently runs:
  - `frontend`
  - `api`
  - `postgres`
  - `redis`
  - `mlflow`
- API runs on `8000`
- Frontend runs on `3000`
- MLflow runs on `5055`
- Postgres was provisioned early, then work item/audit persistence was started on SQL.

## Postgres Migration Progress
- Began migrating persistence away from pure file-backed work items.
- Added DB engine/session/models and SQL repositories.
- Work items and audit events now use SQL-backed repositories.
- Raw document files and exports still remain in file/object-style storage under `storage/`.
- The app still has a local SQLite fallback when `psycopg` is unavailable outside Docker.

## AGENTS / Project Docs
- Added `AGENTS.md` as a contributor guide.
- Later updated `AGENTS.md` to match the newer repo state:
  - Docker services
  - SQL-backed work item persistence
  - frontend app
  - MLflow/evaluation support
  - current architecture boundaries

## Core Refactor

### Problem
- `core/` had become too fragmented.
- Even with only one workflow implemented, the repo had many tiny directories:
  - `core/intake`
  - `core/extraction`
  - `core/review_engine`
  - `core/workflow_registry`
  - `core/document_processing`
  - `core/storage`
  - `core/database`
  - etc.
- This would scale poorly once more workflows are added.

### Refactor Performed
- Reorganized `core/` into broader platform areas:
  - `core/documents`
  - `core/domain`
  - `core/persistence`
  - `core/runtime`
  - `core/workflows`
- Moved existing code into those areas and updated imports across:
  - API
  - tests
  - workflow package
  - runtime code
- Removed old legacy micro-packages.
- Fixed a circular-import issue caused by convenience re-export `__init__.py` files by replacing them with lightweight package docstrings.

### Result
- `core/` is now organized more like a reusable platform layer and less like a pile of feature folders.
- This should make it much easier to add future workflows without making the root platform messy.

## Testing and Verification Performed
- Repeatedly ran `pytest -q`
- Repeatedly ran `python3 -m compileall ...`
- Repeatedly ran `npm run build` in `apps/frontend`
- Repeatedly ran `docker compose config`
- Verified OCR behavior with:
  - plain text uploads
  - image upload using Tesseract
- Verified extraction with:
  - deterministic fallback
  - DeepSeek-backed extraction
- Verified review and export audit flow
- Final verified state at end of session:
  - backend tests passing: `13 passed`
  - frontend production build passing

## Key Product / Behavior Decisions Made
- Keep workflow-specific logic inside `workflows/invoice_autoposting/`
- Keep `core/` generic and reusable
- Make validation the routing decision point
- Make review exception-driven, not mandatory
- Auto-export clean items
- Auto-extract on upload
- Use a workflow selection page before entering a workflow HUD

## Open Technical Gaps / Future Work
- Complete full Postgres migration for all runtime state and remove fallback behavior when ready
- Decide whether upload should also auto-validate in the future
- Improve OCR normalization and confidence handling
- Tighten numeric formatting for exported and extracted amounts
- Implement true MCP usage inside workflow execution
- Add more workflows beyond `invoice_autoposting`
- Add proper DB migrations instead of relying on schema initialization
- Potentially expand feedback/review correction loops into eval and observability tracking

## End State of Session
- OPSFoundry now has a working multi-step but mostly automated invoice workflow:
  - upload
  - OCR
  - extraction
  - validation
  - auto-export for clean documents
  - review queue for exceptions
  - approve/reject for queued items
  - audit history
  - frontend workflow HUD
- The codebase is materially cleaner than it was at the start of the session.
