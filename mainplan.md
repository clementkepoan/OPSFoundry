# PLAN.md

## Objective

Build a **modular AI operations platform** where business workflows can be added as **plug‑and‑play modules**.

The platform will demonstrate a real business automation scenario using **invoice / reimbursement autoposting** as the first workflow.

Architecture must support future workflows without modifying the core system.

Core requirements:

* LangChain for orchestration
* DeepSeek API as the LLM
* MCP tool interfaces
* MLOps tracking
* Docker-based local deployment
* Feature modules that plug into a workflow registry

---

# Platform Philosophy

The project is **not a single application**.

It is a **workflow platform**.

Core platform components remain stable while new business features are implemented as **workflow plugins**.

Example future workflows:

* invoice_autoposting
* treasury_cash_position
* contract_risk_review
* trade_lead_intelligence

Adding a new feature should only require creating a new folder in `workflows/`.

---

# Platform Architecture

```
Frontend Dashboard
        |
        v
FastAPI Gateway
        |
        v
LangChain Workflow Engine
        |
        v
Workflow Registry
        |
        |-------------------------------|
        |               |               |
        v               v               v
Workflow Plugin   Workflow Plugin   Workflow Plugin
(invoice)         (treasury)        (contracts)
        |
        v
MCP Tool Layer
        |
        v
Storage + MLOps
```

Core system does **not know business logic**.

Business logic lives inside **workflow plugins**.

---

# Core Platform Components

## 1 Frontend Dashboard

Generic UI components:

* Upload page
* Work item list
* Document viewer
* Review queue
* Dashboard metrics

These components work for all workflows.

Workflow-specific UI configuration comes from workflow modules.

---

## 2 API Gateway

Responsibilities:

* file upload
* work item creation
* review actions
* export endpoints

API layer must remain **workflow agnostic**.

---

## 3 LangChain Workflow Engine

Central orchestration layer.

Responsibilities:

* run workflow steps
* call DeepSeek models
* call MCP tools
* manage workflow state
* retry failed steps

Each workflow defines its own step pipeline.

---

## 4 Workflow Registry

Maps workflow names to implementations.

Example:

```
registry = {
  "invoice_autoposting": InvoiceWorkflow,
  "treasury_cash_position": TreasuryWorkflow
}
```

The orchestrator loads workflows dynamically.

---

## 5 MCP Tool Layer

External integrations exposed as tools.

Examples:

* chart_of_accounts lookup
* vendor lookup
* FX lookup
* document retrieval
* database query

Agents call these tools through LangChain.

---

## 6 Storage

* Postgres → workflow state
* Redis → queue / caching
* Object storage → uploaded documents

---

## 7 MLOps Layer

Tracks:

* prompts
* runs
* evaluations
* model outputs

Tools:

* MLflow

---

# Workflow Plugin Design

Each workflow must implement the same structure.

Example:

```
workflows/invoice_autoposting/

config.yaml
workflow.py
schemas.py
validators.py
tools.py
prompts.py
```

Workflow plugin responsibilities:

* define steps
* define schemas
* define validation rules
* define required tools
* define export format

---

# Workflow Contract

Every workflow must declare:

```yaml
workflow_name: invoice_autoposting

states:
  - uploaded
  - parsed
  - extracted
  - validated
  - needs_review
  - approved
  - rejected
  - exported

input_schema: document_upload

output_schema: accounting_entry

tools:
  - chart_of_accounts
  - vendor_lookup

validators:
  - totals_match
  - required_fields_present
  - valid_date

exports:
  - csv
  - json
```

The platform executes these steps automatically.

---

# First Workflow (MVP)

Implement **invoice_autoposting**.

Pipeline:

1 upload document
2 parse text (OCR if needed)
3 extract fields via DeepSeek
4 validate fields
5 mark anomalies
6 send to review queue
7 reviewer edits or approves
8 export entry

---

# LangChain Agent Design

LangChain agent responsibilities:

* structured extraction
* classification
* explanation
* tool usage

DeepSeek API used for:

* extraction
* reasoning
* explanations

All outputs must follow strict JSON schema.

---

# Repository Structure

```
ai-ops-platform/

PLAN.md
README.md

docker-compose.yml
Makefile

apps/
  frontend/
  api/

core/
  workflow_registry/
  orchestration/
  tool_runtime/
  review_engine/
  audit/
  exports/
  observability/

workflows/
  invoice_autoposting/
  treasury_cash_position/
  contract_risk_review/

mcp_servers/
  coa_tool/
  vendor_tool/
  fx_tool/

mlops/
  prompts/
  eval_sets/
  tracking/

storage/
  sample_docs/
  synthetic/
```

---

# Data Sources

Public document datasets:

* CORD
* SROIE
* FUNSD
* XFUND

Synthetic company data:

* chart_of_accounts.csv
* vendors.csv
* cost_centers.csv
* mock receipts
* export templates

---

# One Week Build Plan

Day 1

Create repo

Docker stack

FastAPI skeleton

LangChain environment

Workflow registry

Day 2

Upload system

Document storage

OCR abstraction

Work item model

Day 3

LangChain extraction agent

DeepSeek integration

JSON schema outputs

Day 4

Validation rules

Anomaly detection

Review queue

Day 5

Export module

CSV export

Audit logs

Day 6

MLflow integration

Eval dataset

Improve modular boundaries

Day 7

Seed demo data

Polish UI

Test end-to-end

---

# Definition of Done

System runs locally via Docker.

Invoice workflow works end-to-end.

Extraction → validation → review → export works.

All steps logged.

Adding a new workflow requires only adding a folder in `workflows/`.

Core platform code remains unchanged.

---

# Codex Execution Rules

1 Never hardcode business logic in the API layer.

2 All workflow logic must live in `workflows/`.

3 All external integrations must go through MCP tools.

4 LangChain orchestration lives only in `core/orchestration`.

5 DeepSeek outputs must follow JSON schema.

6 Validation rules must remain deterministic.

---

# First Files Codex Should Generate

README.md

docker-compose.yml

apps/api/main.py

core/workflow_registry/registry.py

core/orchestration/langchain_engine.py

workflows/invoice_autoposting/config.yaml

workflows/invoice_autoposting/schemas.py

workflows/invoice_autoposting/validators.py

mcp_servers/coa_tool/server.py

mlops/eval_sets/invoice_eval.json

---

# Initial Pipeline

Codex should implement this flow:

upload_document()

create_work_item()

run_langchain_workflow()

extract_fields()

validate_fields()

flag_anomalies()

send_to_review()

approve_item()

export_entry()

---

# Future Feature Modules

After MVP, add:

```
workflows/treasury_cash_position
workflows/contract_risk_review
workflows/trade_lead_intelligence
```

These workflows plug into the same platform without modifying core modules.
