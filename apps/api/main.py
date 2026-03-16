from fastapi import FastAPI, HTTPException

from core.config.settings import get_settings
from core.orchestration.langchain_engine import LangChainWorkflowEngine
from core.workflow_registry.registry import get_registry

settings = get_settings()
registry = get_registry()
engine = LangChainWorkflowEngine(settings=settings)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    summary="Workflow-agnostic gateway for OPSFoundry",
)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "environment": settings.app_env,
        "status": "ok",
    }


@app.get("/health", tags=["system"])
def healthcheck() -> dict[str, object]:
    return {
        "status": "ok",
        "langchain_ready": engine.is_ready(),
        "registered_workflows": registry.names(),
    }


@app.get("/api/v1/workflows", tags=["workflows"])
def list_workflows() -> list[dict[str, object]]:
    return [workflow.metadata.model_dump(mode="json") for workflow in registry.all()]


@app.get("/api/v1/workflows/{workflow_name}", tags=["workflows"])
def get_workflow(workflow_name: str) -> dict[str, object]:
    try:
        workflow = registry.get(workflow_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown workflow '{workflow_name}'") from exc

    return {
        "metadata": workflow.metadata.model_dump(mode="json"),
        "step_pipeline": workflow.step_pipeline(),
        "runtime": engine.describe_runtime(),
    }
