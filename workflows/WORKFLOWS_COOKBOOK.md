# Workflows Cookbook

This cookbook explains how to build and extend workflow plugins in OPSFoundry.

## 1. Workflow Plugin Contract

Each workflow lives in `workflows/<workflow_name>/` and must expose `get_workflow()` from `workflow.py`.

Required files in practice:
- `workflow.py`: `BaseWorkflow` implementation
- `config.yaml`: workflow metadata (states, exports, categories, fields, languages)
- `schemas.py`: output schema
- `prompts.py`: extraction system prompt
- `parser.py`: deterministic fallback extractor
- `validators.py`: validation + anomaly logic
- `exports.py`: CSV/JSON row mapping

The registry auto-discovers `workflows/*/workflow.py` via `core/workflows/registry.py`.

## 2. Metadata-Driven Modularity

`config.yaml` now supports:
- `invoice_categories`
- `extractable_fields`
- `supported_languages`
- `default_target_currency`

These are surfaced in the UI and consumed by upload APIs:
- `POST /api/v1/workflows/{workflow_name}/documents`
- `POST /api/v1/workflows/{workflow_name}/documents/bulk`

Upload form-data controls:
- `category` (required)
- `extract_fields` (comma-separated)
- `include_line_items` (`true`/`false`)
- `source_language` (`auto`, `en`, etc.)
- `target_currency` (3-letter code)

## 3. Runtime Flow

Current invoice flow is:
1. Upload + OCR
2. Extraction (LLM or fallback parser)
3. Validation
4. If passed -> auto-export
5. If failed/anomaly -> review queue

CSV export is category-specific:
`{workflow_name}_{category}_portfolio.csv`

## 4. Adding a New Workflow

1. Create `workflows/<new_name>/` with files above.
2. Implement `get_workflow()` in `workflow.py`.
3. Define schema and fallback parser first; LLM is optional.
4. Add validators and export row mapping.
5. Add tests under `tests/`.

## 5. Quick Validation Commands

```bash
pytest -q
curl http://localhost:8000/api/v1/workflows
curl http://localhost:8000/api/v1/workflows/invoice_autoposting
```

