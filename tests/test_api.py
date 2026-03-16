from core.runtime.request_guard import build_upload_request_key, build_work_item_request_key


def test_healthcheck_exposes_registered_workflows(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "invoice_autoposting" in payload["registered_workflows"]


def test_upload_creates_work_item_and_supports_download(client) -> None:
    payload = (
        b"Acme Office Supply\n"
        b"Invoice Number: INV-1001\n"
        b"Invoice Date: 2025-01-15\n"
        b"Currency: USD\n"
        b"Subtotal: 120.00\n"
        b"Tax: 5.50\n"
        b"Total: 125.50\n"
    )

    response = client.post(
        "/api/v1/workflows/invoice_autoposting/documents",
        files={"file": ("invoice.txt", payload, "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document"]["filename"] == "invoice.txt"
    assert body["ocr"]["status"] == "text_extracted"
    assert body["work_item"]["ocr_text"].startswith("Acme Office Supply")
    assert body["work_item"]["state"] == "exported"
    assert body["validation"]["status"] == "passed"
    assert body["artifact"]["filename"] == "invoice_autoposting_portfolio.csv"
    assert body["work_item"]["document_id"] == body["document"]["id"]
    assert body["extraction"]["status"] == "succeeded"
    assert body["work_item"]["extracted_data"]["invoice_number"] == "INV-1001"
    assert body["work_item"]["metadata"]["ocr_warnings"] == []

    work_items_response = client.get("/api/v1/work-items")
    assert work_items_response.status_code == 200
    assert len(work_items_response.json()) == 1

    download_response = client.get(f"/api/v1/documents/{body['document']['id']}/download")
    assert download_response.status_code == 200
    assert download_response.content == payload


def test_upload_rejects_binary_when_ocr_is_unavailable_or_fails(client) -> None:
    response = client.post(
        "/api/v1/workflows/invoice_autoposting/documents",
        files={"file": ("invoice.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code in {422, 503}
    assert "OCR failed" in response.json()["detail"]
    work_items_response = client.get("/api/v1/work-items")
    assert work_items_response.status_code == 200
    assert work_items_response.json() == []


def test_duplicate_upload_request_returns_conflict(client) -> None:
    payload = b"Invoice INV-1001\nTotal: 125.50\n"
    request_key = build_upload_request_key(
        workflow_name="invoice_autoposting",
        filename="invoice.txt",
        content_type="text/plain",
        size_bytes=len(payload),
    )
    assert client.app.state.request_guard.claim(
        request_key,
        client.app.state.settings.duplicate_request_ttl_seconds,
    )

    response = client.post(
        "/api/v1/workflows/invoice_autoposting/documents",
        files={"file": ("invoice.txt", payload, "text/plain")},
    )

    assert response.status_code == 409
    assert "duplicate request" in response.json()["detail"].lower()


def test_download_returns_not_found_when_file_is_missing(client) -> None:
    response = client.post(
        "/api/v1/workflows/invoice_autoposting/documents",
        files={"file": ("invoice.txt", b"hello", "text/plain")},
    )
    document_id = response.json()["document"]["id"]
    object_key = response.json()["document"]["object_key"]
    (client.app.state.settings.document_storage_dir / object_key).unlink()

    download_response = client.get(f"/api/v1/documents/{document_id}/download")

    assert download_response.status_code == 404
    assert "Stored file for document" in download_response.json()["detail"]


def test_extract_work_item_returns_structured_invoice_payload(client) -> None:
    invoice_text = (
        "Acme Office Supply\n"
        "Invoice Number: INV-1001\n"
        "Invoice Date: 2025-01-15\n"
        "Currency: USD\n"
        "Subtotal: 120.00\n"
        "Tax: 5.50\n"
        "Total: 125.50\n"
        "Payment Terms: Net 30\n"
    )
    upload_response = client.post(
        "/api/v1/workflows/invoice_autoposting/documents",
        files={"file": ("invoice.txt", invoice_text.encode("utf-8"), "text/plain")},
    )
    work_item_id = upload_response.json()["work_item"]["id"]

    extract_response = client.post(f"/api/v1/work-items/{work_item_id}/extract")

    assert extract_response.status_code == 200
    body = extract_response.json()
    assert body["extraction"]["status"] == "succeeded"
    assert body["extraction"]["backend"] == "deterministic_fallback"
    assert body["work_item"]["state"] == "extracted"
    assert body["work_item"]["extracted_data"]["invoice_number"] == "INV-1001"
    assert body["work_item"]["extracted_data"]["vendor_name"] == "Acme Office Supply"
    assert body["work_item"]["extracted_data"]["total_amount"] == "125.50"


def test_validate_passes_without_review_for_clean_invoice(client) -> None:
    invoice_text = (
        "Acme Office Supply\n"
        "Invoice Number: INV-1002\n"
        "Invoice Date: 2025-01-15\n"
        "Currency: USD\n"
        "Subtotal: 120.00\n"
        "Tax: 5.50\n"
        "Total: 125.50\n"
    )
    upload_response = client.post(
        "/api/v1/workflows/invoice_autoposting/documents",
        files={"file": ("invoice.txt", invoice_text.encode("utf-8"), "text/plain")},
    )
    assert upload_response.status_code == 201
    body = upload_response.json()
    work_item_id = body["work_item"]["id"]
    assert body["validation"]["status"] == "passed"
    assert body["work_item"]["state"] == "exported"
    assert body["work_item"]["review_status"] == "not_required"
    assert body["work_item"]["export_status"] == "completed"
    assert body["artifact"]["filename"] == "invoice_autoposting_portfolio.csv"

    queue_response = client.get("/api/v1/review-queue")
    assert queue_response.status_code == 200
    assert queue_response.json() == []

    csv_response = client.get("/api/v1/workflows/invoice_autoposting/exports/csv/download")
    assert csv_response.status_code == 200
    csv_text = csv_response.text
    assert "work_item_id" in csv_text
    assert "source_filename" in csv_text
    assert work_item_id in csv_text


def test_validate_queues_zero_value_invoice_for_review(client) -> None:
    invoice_text = (
        "Acme Office Supply\n"
        "Invoice Number: INV-0000\n"
        "Invoice Date: 2025-01-15\n"
        "Currency: USD\n"
        "Subtotal: 0.00\n"
        "Tax: 0.00\n"
        "Total: 0.00\n"
    )
    upload_response = client.post(
        "/api/v1/workflows/invoice_autoposting/documents",
        files={"file": ("invoice.txt", invoice_text.encode("utf-8"), "text/plain")},
    )
    assert upload_response.status_code == 201
    body = upload_response.json()
    assert body["validation"]["status"] == "needs_review"
    assert body["work_item"]["state"] == "needs_review"
    assert body["work_item"]["review_status"] == "queued"
    assert any(result["name"] == "meaningful_amounts" and not result["passed"] for result in body["validation"]["results"])
    assert body["artifact"] is None


def test_validate_review_approve_auto_export_and_audit_flow(client) -> None:
    invoice_text = (
        "Acme Office Supply\n"
        "Invoice Number: INV-1003\n"
        "Invoice Date: 2025-01-15\n"
        "Currency: USD\n"
        "Subtotal: 120.00\n"
        "Tax: 5.50\n"
        "Total: 120.00\n"
    )
    upload_response = client.post(
        "/api/v1/workflows/invoice_autoposting/documents",
        files={"file": ("invoice.txt", invoice_text.encode("utf-8"), "text/plain")},
    )
    assert upload_response.status_code == 201
    validation_body = upload_response.json()
    work_item_id = validation_body["work_item"]["id"]
    assert validation_body["validation"]["status"] == "needs_review"
    assert validation_body["work_item"]["state"] == "needs_review"
    assert validation_body["work_item"]["review_status"] == "queued"
    assert validation_body["work_item"]["anomaly_flags"]

    queue_response = client.get("/api/v1/review-queue")
    assert queue_response.status_code == 200
    assert queue_response.json()[0]["id"] == work_item_id

    review_response = client.post(
        f"/api/v1/work-items/{work_item_id}/review",
        json={"action": "approve", "review_notes": "Manual approval after review."},
    )
    assert review_response.status_code == 200
    review_body = review_response.json()
    assert review_body["work_item"]["state"] == "exported"
    assert review_body["work_item"]["review_status"] == "approved"
    assert review_body["work_item"]["export_status"] == "completed"
    assert review_body["artifact"]["filename"] == "invoice_autoposting_portfolio.csv"

    audit_response = client.get(f"/api/v1/work-items/{work_item_id}/audit")
    assert audit_response.status_code == 200
    event_types = [event["event_type"] for event in audit_response.json()]
    assert event_types == [
        "document_uploaded",
        "fields_extracted",
        "fields_validated",
        "review_approve",
        "work_item_exported",
    ]


def test_review_requires_item_to_be_in_review_queue(client) -> None:
    invoice_text = (
        "Acme Office Supply\n"
        "Invoice Number: INV-1004\n"
        "Invoice Date: 2025-01-15\n"
        "Currency: USD\n"
        "Subtotal: 120.00\n"
        "Tax: 5.50\n"
        "Total: 125.50\n"
    )
    upload_response = client.post(
        "/api/v1/workflows/invoice_autoposting/documents",
        files={"file": ("invoice.txt", invoice_text.encode("utf-8"), "text/plain")},
    )
    work_item_id = upload_response.json()["work_item"]["id"]

    review_response = client.post(
        f"/api/v1/work-items/{work_item_id}/review",
        json={"action": "approve", "review_notes": "Should fail."},
    )

    assert review_response.status_code == 400
    assert "review queue" in review_response.json()["detail"]


def test_duplicate_validate_request_returns_conflict(client) -> None:
    invoice_text = (
        "Acme Office Supply\n"
        "Invoice Number: INV-1005\n"
        "Invoice Date: 2025-01-15\n"
        "Currency: USD\n"
        "Subtotal: 120.00\n"
        "Tax: 5.50\n"
        "Total: 125.50\n"
    )
    upload_response = client.post(
        "/api/v1/workflows/invoice_autoposting/documents",
        files={"file": ("invoice.txt", invoice_text.encode("utf-8"), "text/plain")},
    )
    work_item_id = upload_response.json()["work_item"]["id"]
    request_key = build_work_item_request_key(action="validate", work_item_id=work_item_id)
    assert client.app.state.request_guard.claim(
        request_key,
        client.app.state.settings.duplicate_request_ttl_seconds,
    )

    validate_response = client.post(f"/api/v1/work-items/{work_item_id}/validate")

    assert validate_response.status_code == 409
    assert "duplicate request" in validate_response.json()["detail"].lower()


def test_delete_work_item_removes_item_and_document(client) -> None:
    upload_response = client.post(
        "/api/v1/workflows/invoice_autoposting/documents",
        files={"file": ("invoice.txt", b"hello", "text/plain")},
    )
    body = upload_response.json()
    work_item_id = body["work_item"]["id"]
    document_id = body["document"]["id"]

    delete_response = client.delete(f"/api/v1/work-items/{work_item_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_work_item_id"] == work_item_id
    assert delete_response.json()["deleted_document_id"] == document_id

    get_work_item_response = client.get(f"/api/v1/work-items/{work_item_id}")
    assert get_work_item_response.status_code == 404

    get_document_response = client.get(f"/api/v1/documents/{document_id}")
    assert get_document_response.status_code == 404
