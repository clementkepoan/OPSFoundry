# OPSFoundry

OPSFoundry is a modular AI operations platform for business workflow automation.

The initial workflow is `invoice_autoposting`, but the platform is structured so new workflows can be added under `workflows/` without changing the core orchestration or API layers.

## Day 1 Scope

This repository currently includes:

- Docker-based local stack scaffold
- FastAPI application skeleton
- LangChain and DeepSeek environment wiring
- Dynamic workflow registry
- Initial `invoice_autoposting` plugin contract

## Quick Start

1. Copy `.env.example` to `.env`.
2. Build and start the stack:

```bash
docker compose up --build
```

3. Open the API docs at `http://localhost:8000/docs`.

## Project Structure

```text
apps/
  api/
core/
  config/
  orchestration/
  workflow_registry/
workflows/
  invoice_autoposting/
mcp_servers/
  coa_tool/
mlops/
  eval_sets/
```

## Planned Delivery Sequence

- Day 1: scaffold platform and registry
- Day 2: upload system and work item model
- Day 3: extraction agent and DeepSeek structured outputs
- Day 4: validators, anomalies, review queue
- Day 5: exports and audit logging
- Day 6: MLflow tracking and evaluation
- Day 7: demo data, UI polish, end-to-end testing
