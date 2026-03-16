def test_observability_status_and_eval_runner(client) -> None:
    status_response = client.get("/api/v1/observability/status")

    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["backend"] in {"file", "mlflow"}

    eval_response = client.post("/api/v1/evals/invoice_autoposting/run", params={"mode": "fallback"})

    assert eval_response.status_code == 200
    body = eval_response.json()
    assert body["workflow_name"] == "invoice_autoposting"
    assert body["mode"] == "fallback"
    assert body["total_cases"] >= 1
    assert body["passed_cases"] >= 1
    assert body["field_accuracy"] == 1.0
