# MCP Server Cookbook

This cookbook covers MCP-style tool servers inside OPSFoundry.

## 1. Current State in This Repo

Current MCP folder:
- `mcp_servers/coa_tool/server.py`

`coa_tool` provides a local chart-of-accounts lookup utility with:
- `AccountRecord` (Pydantic model)
- static `CHART_OF_ACCOUNTS`
- `lookup_chart_of_accounts(query: str)`

This is a tool-ready module and can be wired into agent/tool orchestration as needed.

## 2. Suggested Server Layout

For each server:
- `mcp_servers/<server_name>/__init__.py`
- `mcp_servers/<server_name>/server.py`
- optional `schemas.py` and `tests/`

Keep tool functions pure and typed so they can be called from:
- workflow extract/review stages
- future MCP transport adapters
- API wrappers

## 3. Implementation Guidelines

1. Define request/response models with Pydantic.
2. Keep side effects isolated (DB/network behind a small adapter layer).
3. Return deterministic outputs for identical inputs.
4. Validate and normalize tool inputs early.
5. Raise clear errors (or return structured error payloads).

## 4. Wiring a Tool Into Workflows

Recommended pattern:
1. Implement tool in `mcp_servers/<name>/server.py`.
2. Reference tool in workflow metadata (`tools:` in `config.yaml`).
3. Call tool from extraction/review runtime layer where needed.
4. Persist tool decisions in `work_item.metadata` for traceability.

## 5. Local Sanity Check

Example quick check in Python shell:

```python
from mcp_servers.coa_tool.server import lookup_chart_of_accounts
print(lookup_chart_of_accounts("office"))
```

Then run:

```bash
pytest -q
```

