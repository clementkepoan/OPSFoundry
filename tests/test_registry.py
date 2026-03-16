from core.workflows.registry import get_registry


def test_registry_discovers_invoice_workflow() -> None:
    registry = get_registry()

    workflow = registry.get("invoice_autoposting")
    assert workflow.metadata.name == "invoice_autoposting"
    assert "validate_fields" in workflow.step_pipeline()
