"use client";

import { ChangeEvent, FormEvent, startTransition, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { API_BASE_URL, apiDelete, apiGet, apiPost } from "../lib/api";
import styles from "./dashboard.module.css";

type WorkflowMetadata = {
  name: string;
  description: string;
  states: string[];
  invoice_categories?: string[];
  extractable_fields?: string[];
  supported_languages?: string[];
  default_target_currency?: string;
};

type WorkflowDetail = {
  metadata: WorkflowMetadata;
  step_pipeline: string[];
};

type ValidationResult = {
  name: string;
  passed: boolean;
  message?: string | null;
};

type AnomalyFlag = {
  code: string;
  severity: string;
  message: string;
};

type ExportArtifact = {
  format: string;
  filename: string;
  path: string;
};

type WorkItem = {
  id: string;
  workflow_name: string;
  category: string;
  state: string;
  document_id: string;
  filename: string;
  content_type: string;
  created_at: string;
  updated_at: string;
  review_status: string;
  review_notes?: string | null;
  export_status: string;
  extraction_status: string;
  extraction_backend?: string | null;
  validation_status: string;
  ocr_status: string;
  ocr_backend?: string | null;
  exported_artifact?: ExportArtifact | null;
  extracted_data?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
  validation_results: ValidationResult[];
  anomaly_flags: AnomalyFlag[];
};

type AuditEvent = {
  timestamp: string;
  event_type: string;
  actor: string;
  payload: Record<string, unknown>;
};

type ObservabilityStatus = {
  backend: string;
  tracking_uri?: string;
  path?: string;
  experiment_name?: string;
  audit_backend: string;
};

type UploadReceipt = {
  work_item: WorkItem;
  extraction: {
    status: string;
    backend: string;
  };
  validation?: {
    status: string;
    results: ValidationResult[];
    anomalies: AnomalyFlag[];
  } | null;
  artifact?: ExportArtifact | null;
};

type ValidationResponse = {
  work_item: WorkItem;
  validation: {
    status: string;
    results: ValidationResult[];
    anomalies: AnomalyFlag[];
  };
  artifact: ExportArtifact | null;
};

type ReviewResponse = {
  work_item: WorkItem;
  artifact: ExportArtifact | null;
};

type DeleteResponse = {
  deleted_work_item_id: string;
  deleted_document_id: string;
  removed_csv_rows?: number;
};

type BulkProgressState = {
  total: number;
  completed: number;
  succeeded: number;
  failed: number;
  currentFile: string | null;
};

type ActionOutcome = {
  message?: string;
  focusId?: string | null;
};

const dateFormatter = new Intl.DateTimeFormat("en", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

function formatTimestamp(value: string): string {
  return dateFormatter.format(new Date(value));
}

function humanizeStatus(value: string | null | undefined): string {
  if (!value) return "n/a";
  return value.replace(/_/g, " ");
}

function idempotencyHeader(key: string): HeadersInit {
  return { "X-Idempotency-Key": key };
}

function nextAction(item: WorkItem): string {
  if (item.extraction_status !== "succeeded") return "Check extraction";
  if (item.review_status === "queued" || item.state === "needs_review") return "Resolve review";
  if (item.export_status === "completed") return "Exported";
  if (item.validation_status !== "passed") return "Validate";
  return "Ready";
}

function itemTone(item: WorkItem): "queue" | "success" | "default" {
  if (item.review_status === "queued" || item.state === "needs_review") return "queue";
  if (item.export_status === "completed") return "success";
  return "default";
}

function stageState(item: WorkItem, stage: "extract" | "validate" | "review" | "export"): string {
  if (stage === "extract") {
    return item.extraction_status === "succeeded" ? "done" : "current";
  }
  if (stage === "validate") {
    if (item.validation_status === "passed" || item.validation_status === "needs_review") return "done";
    return item.extraction_status === "succeeded" ? "current" : "pending";
  }
  if (stage === "review") {
    if (item.review_status === "approved" || item.review_status === "rejected" || item.review_status === "not_required") {
      return "done";
    }
    if (item.review_status === "queued" || item.state === "needs_review") return "current";
    return "pending";
  }
  if (item.export_status === "completed") return "done";
  if (item.validation_status === "passed" || item.review_status === "approved") return "current";
  return "pending";
}

export function Dashboard({ workflowName }: { workflowName: string }) {
  const router = useRouter();
  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [reviewQueue, setReviewQueue] = useState<WorkItem[]>([]);
  const [observability, setObservability] = useState<ObservabilityStatus | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Loading workflow HUD...");
  const [reviewNotes, setReviewNotes] = useState("");
  const [editedDataText, setEditedDataText] = useState("{}");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [sourceLanguage, setSourceLanguage] = useState("auto");
  const [targetCurrency, setTargetCurrency] = useState("USD");
  const [includeLineItems, setIncludeLineItems] = useState(true);
  const [bulkProgress, setBulkProgress] = useState<BulkProgressState | null>(null);
  const [customCategories, setCustomCategories] = useState<string[]>([]);

  const selectedItem = useMemo(
    () => workItems.find((item) => item.id === selectedId) ?? reviewQueue.find((item) => item.id === selectedId) ?? null,
    [reviewQueue, selectedId, workItems],
  );
  const availableCategories = useMemo(() => {
    const categories = new Set<string>();
    for (const category of workflow?.metadata.invoice_categories ?? []) {
      if (category) categories.add(category);
    }
    for (const category of customCategories) {
      if (category) categories.add(category);
    }
    for (const item of workItems) {
      if (item.category) categories.add(item.category);
    }
    for (const item of reviewQueue) {
      if (item.category) categories.add(item.category);
    }
    if (selectedCategory) categories.add(selectedCategory);
    return Array.from(categories).sort();
  }, [customCategories, reviewQueue, selectedCategory, workItems, workflow?.metadata.invoice_categories]);

  useEffect(() => {
    const key = `opsfoundry:categories:${workflowName}`;
    try {
      const raw = window.localStorage.getItem(key);
      if (!raw) {
        setCustomCategories([]);
        return;
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        setCustomCategories([]);
        return;
      }
      const normalized = parsed
        .filter((value): value is string => typeof value === "string")
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean);
      setCustomCategories(Array.from(new Set(normalized)).sort());
    } catch {
      setCustomCategories([]);
    }
  }, [workflowName]);

  useEffect(() => {
    const key = `opsfoundry:categories:${workflowName}`;
    try {
      window.localStorage.setItem(key, JSON.stringify(customCategories));
    } catch {
      return;
    }
  }, [customCategories, workflowName]);

  async function refreshAll(preferredId?: string | null) {
    const encodedWorkflow = encodeURIComponent(workflowName);
    const [workflowData, workItemData, reviewData, observabilityData] = await Promise.all([
      apiGet<WorkflowDetail>(`/api/v1/workflows/${encodedWorkflow}`),
      apiGet<WorkItem[]>(`/api/v1/work-items?workflow_name=${encodedWorkflow}`),
      apiGet<WorkItem[]>(`/api/v1/review-queue?workflow_name=${encodedWorkflow}`),
      apiGet<ObservabilityStatus>("/api/v1/observability/status"),
    ]);

    setWorkflow(workflowData);
    setWorkItems(workItemData);
    setReviewQueue(reviewData);
    setObservability(observabilityData);

    if (!selectedCategory) {
      const inferredCategory =
        reviewData[0]?.category ??
        workItemData[0]?.category ??
        workflowData.metadata.invoice_categories?.[0] ??
        "";
      setSelectedCategory(inferredCategory);
    }
    if (selectedFields.length === 0 && workflowData.metadata.extractable_fields?.length) {
      setSelectedFields(workflowData.metadata.extractable_fields);
    }
    if (workflowData.metadata.default_target_currency) {
      setTargetCurrency(workflowData.metadata.default_target_currency);
    }
    if (!sourceLanguage && workflowData.metadata.supported_languages?.length) {
      const defaultLanguage = workflowData.metadata.supported_languages.includes("auto")
        ? "auto"
        : workflowData.metadata.supported_languages[0];
      setSourceLanguage(defaultLanguage);
    }

    const nextId = preferredId ?? selectedId ?? reviewData[0]?.id ?? workItemData[0]?.id ?? null;
    setSelectedId(nextId);

    if (!nextId) {
      setAuditEvents([]);
      return;
    }

    const audit = await apiGet<AuditEvent[]>(`/api/v1/work-items/${nextId}/audit`);
    setAuditEvents(audit);
  }

  useEffect(() => {
    void refreshAll().then(
      () => setStatusMessage("Workflow HUD ready. Upload now triggers extraction automatically."),
      (error: Error) => setStatusMessage(error.message),
    );
  }, [workflowName]);

  useEffect(() => {
    if (!selectedId) {
      setAuditEvents([]);
      return;
    }

    void apiGet<AuditEvent[]>(`/api/v1/work-items/${selectedId}/audit`).then(
      setAuditEvents,
      (error: Error) => setStatusMessage(error.message),
    );
  }, [selectedId]);

  useEffect(() => {
    if (!selectedItem) {
      setReviewNotes("");
      setEditedDataText("{}");
      return;
    }
    setReviewNotes(selectedItem.review_notes ?? "");
    setEditedDataText(JSON.stringify(selectedItem.extracted_data ?? {}, null, 2));
  }, [selectedItem?.id]);

  async function performAction<T>(
    label: string,
    action: () => Promise<T>,
    onSuccess?: (result: T) => ActionOutcome | void,
    focusId?: string | null,
  ) {
    setBusy(true);
    setStatusMessage(label);
    try {
      const result = await action();
      const outcome = onSuccess?.(result);
      startTransition(() => {
        void refreshAll(outcome?.focusId ?? focusId ?? selectedId).then(() => {
          setStatusMessage(outcome?.message ?? `${label} complete.`);
        });
      });
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedFiles.length === 0) {
      setStatusMessage("Select one or more source files before uploading.");
      return;
    }
    const normalizedCategory = selectedCategory.trim().toLowerCase();
    if (!normalizedCategory) {
      setStatusMessage("Select an invoice category before uploading.");
      return;
    }
    setCustomCategories((current) =>
      current.includes(normalizedCategory) ? current : [...current, normalizedCategory].sort()
    );

    const formData = new FormData();
    formData.append("category", normalizedCategory);
    formData.append("extract_fields", selectedFields.join(","));
    formData.append("include_line_items", String(includeLineItems));
    formData.append("source_language", sourceLanguage);
    formData.append("target_currency", targetCurrency.toUpperCase());
    if (selectedFiles.length === 1) {
      const onlyFile = selectedFiles[0];
      formData.append("file", onlyFile);
      setBulkProgress(null);

      await performAction<UploadReceipt>(
        `Uploading ${onlyFile.name}`,
        () =>
          apiPost<UploadReceipt>(
            `/api/v1/workflows/${encodeURIComponent(workflowName)}/documents`,
            formData,
            idempotencyHeader(
              `upload:${workflowName}:${normalizedCategory}:${onlyFile.name}:${onlyFile.size}:${onlyFile.lastModified}`,
            ),
          ),
        (receipt) => {
          setSelectedFiles([]);
          const validationStatus = receipt.validation?.status;
          return {
            focusId: receipt.work_item.id,
            message:
              receipt.extraction.status !== "succeeded"
                ? `Uploaded ${onlyFile.name}, but extraction needs attention.`
                : validationStatus === "passed"
                  ? `Uploaded, extracted, validated, and exported ${onlyFile.name}.`
                  : validationStatus === "needs_review"
                    ? `Uploaded and routed ${onlyFile.name} to review queue.`
                    : `Uploaded and extracted ${onlyFile.name}.`,
          };
        },
      );
      return;
    }

    const files = [...selectedFiles];
    let succeeded = 0;
    let failed = 0;
    let focusId: string | null = null;
    setBusy(true);
    setStatusMessage(`Bulk uploading ${files.length} files...`);
    setBulkProgress({
      total: files.length,
      completed: 0,
      succeeded: 0,
      failed: 0,
      currentFile: files[0]?.name ?? null,
    });

    try {
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        setBulkProgress((current) =>
          current
            ? { ...current, currentFile: file.name }
            : {
                total: files.length,
                completed: index,
                succeeded,
                failed,
                currentFile: file.name,
              },
        );

        const singleFormData = new FormData();
        singleFormData.append("category", normalizedCategory);
        singleFormData.append("extract_fields", selectedFields.join(","));
        singleFormData.append("include_line_items", String(includeLineItems));
        singleFormData.append("source_language", sourceLanguage);
        singleFormData.append("target_currency", targetCurrency.toUpperCase());
        singleFormData.append("file", file);

        try {
          const receipt = await apiPost<UploadReceipt>(
            `/api/v1/workflows/${encodeURIComponent(workflowName)}/documents`,
            singleFormData,
            idempotencyHeader(
              `upload:${workflowName}:${normalizedCategory}:${file.name}:${file.size}:${file.lastModified}`,
            ),
          );
          succeeded += 1;
          if (!focusId) {
            focusId = receipt.work_item.id;
          }
        } catch {
          failed += 1;
        }

        setBulkProgress({
          total: files.length,
          completed: index + 1,
          succeeded,
          failed,
          currentFile: index + 1 < files.length ? files[index + 1].name : null,
        });
      }

      setSelectedFiles([]);
      await refreshAll(focusId ?? selectedId);
      setStatusMessage(`Bulk upload complete. ${succeeded} succeeded, ${failed} failed.`);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Bulk upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleExtract() {
    if (!selectedItem) return;
    await performAction(
      `Re-running extraction for ${selectedItem.filename}`,
      () =>
        apiPost(
          `/api/v1/work-items/${selectedItem.id}/extract`,
          undefined,
          idempotencyHeader(`extract:${selectedItem.id}`),
        ),
      () => ({ message: "Extraction finished. Validate to continue routing." }),
      selectedItem.id,
    );
  }

  async function handleValidate() {
    if (!selectedItem) return;
    await performAction<ValidationResponse>(
      `Validating ${selectedItem.filename}`,
      () =>
        apiPost<ValidationResponse>(
          `/api/v1/work-items/${selectedItem.id}/validate`,
          undefined,
          idempotencyHeader(`validate:${selectedItem.id}`),
        ),
      (response) => ({
        message:
          response.validation.status === "passed"
            ? `Validation passed. ${response.artifact?.filename ?? "CSV"} exported automatically.`
            : "Validation routed the item to review.",
      }),
      selectedItem.id,
    );
  }

  async function handleReview(action: "approve" | "reject") {
    if (!selectedItem) return;
    let updatedData: Record<string, unknown> | undefined;
    if (action === "approve") {
      try {
        updatedData = JSON.parse(editedDataText) as Record<string, unknown>;
      } catch {
        setStatusMessage("Edited payload is not valid JSON.");
        return;
      }
    }
    await performAction<ReviewResponse>(
      `${action === "approve" ? "Approving" : "Rejecting"} ${selectedItem.filename}`,
      () =>
        apiPost<ReviewResponse>(`/api/v1/work-items/${selectedItem.id}/review`, {
          action,
          review_notes: reviewNotes || undefined,
          updated_data: action === "approve" ? updatedData : undefined,
        }, idempotencyHeader(`review:${action}:${selectedItem.id}`)),
      (response) => ({
        message:
          action === "approve"
            ? `Approved and exported as ${response.artifact?.filename ?? "CSV"}.`
            : "Work item rejected.",
      }),
      selectedItem.id,
    );
  }

  async function handleDeleteWorkItem(workItemId: string) {
    await performAction<DeleteResponse>(
      `Deleting work item ${workItemId.slice(0, 8)}`,
      () => apiDelete<DeleteResponse>(`/api/v1/work-items/${workItemId}`),
      () => ({
        focusId: null,
        message: "Work item deleted from portfolio.",
      }),
      null,
    );
  }

  function handleDownloadWorkflowCsv() {
    const normalizedCategory = selectedCategory.trim().toLowerCase();
    if (!normalizedCategory) {
      setStatusMessage("Select an invoice category before downloading CSV.");
      return;
    }
    window.open(
      `${API_BASE_URL}/api/v1/workflows/${encodeURIComponent(workflowName)}/exports/csv/download?category=${encodeURIComponent(normalizedCategory)}`,
      "_blank",
      "noopener,noreferrer",
    );
  }

  const metrics = useMemo(() => {
    const total = workItems.length;
    const queued = reviewQueue.length;
    const exported = workItems.filter((item) => item.export_status === "completed").length;
    const straightThrough = workItems.filter(
      (item) => item.validation_status === "passed" && item.review_status === "not_required",
    ).length;
    return [
      { label: "Tracked", value: String(total) },
      { label: "Straight-through", value: String(straightThrough) },
      { label: "In Review", value: String(queued) },
      { label: "Exported", value: String(exported) },
    ];
  }, [reviewQueue.length, workItems]);

  const stageLabels = [
    { key: "extract", label: "Extract" },
    { key: "validate", label: "Validate" },
    { key: "review", label: "Review" },
    { key: "export", label: "Export" },
  ] as const;

  return (
    <main className={styles.shell}>
      <button type="button" className={styles.backButton} onClick={() => router.push("/")}>
        Back to workflows
      </button>
      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <p className={styles.kicker}>{workflow?.metadata.name ?? workflowName}</p>
          <h1>Workflow HUD for exception-driven invoice operations.</h1>
          <p className={styles.lead}>
            {workflow?.metadata.description ??
              "Upload triggers extraction automatically. Validation then sends clean items straight to export and exceptions to review."}
          </p>
          <div className={styles.flowRail}>
            {(workflow?.step_pipeline ?? ["upload", "extract", "validate", "review", "export"]).map((step) => (
              <span key={step}>{humanizeStatus(step)}</span>
            ))}
          </div>
        </div>
        <aside className={styles.heroAside}>
          <div className={styles.endpointCard}>
            <span>Workflow endpoint</span>
            <code>{API_BASE_URL}/api/v1/workflows/{workflowName}</code>
          </div>
          <div className={styles.statusCard}>
            <span>Workflow status</span>
            <strong>{busy ? "Processing" : "Ready"}</strong>
            <p>{statusMessage}</p>
            {bulkProgress ? (
              <div className={styles.progressWrap}>
                <progress
                  className={styles.progressBar}
                  max={bulkProgress.total}
                  value={bulkProgress.completed}
                />
                <small className={styles.progressMeta}>
                  {bulkProgress.completed}/{bulkProgress.total} completed · ok {bulkProgress.succeeded} · failed{" "}
                  {bulkProgress.failed}
                  {bulkProgress.currentFile ? ` · current ${bulkProgress.currentFile}` : ""}
                </small>
              </div>
            ) : null}
          </div>
          <div className={styles.metrics}>
            {metrics.map((metric) => (
              <article key={metric.label} className={styles.metric}>
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </article>
            ))}
          </div>
        </aside>
      </section>

      <section className={styles.layout}>
        <article className={`${styles.panel} ${styles.portfolioPanel}`}>
          <div className={styles.sectionHeader}>
            <div>
              <p className={styles.eyebrow}>Portfolio</p>
              <h2>Work item ledger</h2>
            </div>
            <div className={styles.headerActions}>
              <input
                className={styles.headerSelect}
                list="invoice-category-options"
                value={selectedCategory}
                onChange={(event) => setSelectedCategory(event.target.value)}
                placeholder="Category for CSV"
              />
              <button type="button" className={styles.secondaryButton} onClick={() => void refreshAll(selectedId)}>
                Refresh
              </button>
              <button type="button" className={styles.secondaryButton} onClick={handleDownloadWorkflowCsv}>
                Download CSV
              </button>
            </div>
          </div>
          <datalist id="invoice-category-options">
            {availableCategories.map((category) => (
              <option key={category} value={category} />
            ))}
          </datalist>
          <div className={styles.ledger}>
            {workItems.length === 0 ? (
              <p className={styles.emptyState}>No work items for this workflow yet.</p>
            ) : (
              workItems.map((item) => (
                <article
                  key={item.id}
                  onClick={() => {
                    setSelectedId(item.id);
                    setSelectedCategory(item.category);
                  }}
                  className={`${styles.ledgerCard} ${styles[itemTone(item)]} ${selectedId === item.id ? styles.activeCard : ""}`}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedId(item.id);
                    }
                  }}
                >
                  <div className={styles.ledgerTop}>
                    <div>
                      <strong>{item.filename}</strong>
                      <span>{item.id.slice(0, 8)} · {item.workflow_name}</span>
                    </div>
                    <div className={styles.ledgerActions}>
                      <span className={styles.stateChip}>{humanizeStatus(item.state)}</span>
                      <button
                        type="button"
                        className={styles.deleteButton}
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleDeleteWorkItem(item.id);
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  <div className={styles.ledgerMeta}>
                    <span>OCR: {humanizeStatus(item.ocr_backend)}</span>
                    <span>Category: {humanizeStatus(item.category)}</span>
                    <span>Extraction: {humanizeStatus(item.extraction_status)}</span>
                    <span>Validation: {humanizeStatus(item.validation_status)}</span>
                    <span>Review: {humanizeStatus(item.review_status)}</span>
                  </div>
                  <div className={styles.ledgerFooter}>
                    <span>{nextAction(item)}</span>
                    <small>{formatTimestamp(item.updated_at)}</small>
                  </div>
                </article>
              ))
            )}
          </div>
        </article>

        <div className={styles.lowerGrid}>
          <div className={styles.column}>
          <article className={styles.panel}>
            <div className={styles.sectionHeader}>
              <div>
                <p className={styles.eyebrow}>Intake</p>
                <h2>Upload source</h2>
              </div>
              <span className={styles.pill}>{busy ? "busy" : "live"}</span>
            </div>
            <form className={styles.uploadForm} onSubmit={handleUpload}>
              <label>
                Workflow
                <strong>{workflow?.metadata.name ?? workflowName}</strong>
              </label>
              <label>
                Invoice category
                <input
                  list="invoice-category-options"
                  value={selectedCategory}
                  onChange={(event) => setSelectedCategory(event.target.value)}
                  placeholder="Type or select category"
                />
              </label>
              <label>
                Source language
                <select
                  value={sourceLanguage}
                  onChange={(event) => setSourceLanguage(event.target.value)}
                >
                  {(workflow?.metadata.supported_languages ?? ["auto"]).map((language) => (
                    <option key={language} value={language}>
                      {language.toUpperCase()}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Target currency
                <input
                  maxLength={3}
                  value={targetCurrency}
                  onChange={(event) => setTargetCurrency(event.target.value.toUpperCase())}
                />
              </label>
              <fieldset className={styles.fieldset}>
                <legend>Fields to extract</legend>
                <div className={styles.fieldOptions}>
                  {(workflow?.metadata.extractable_fields ?? []).map((fieldName) => (
                    <label key={fieldName} className={styles.checkboxLabel}>
                      <input
                        type="checkbox"
                        checked={selectedFields.includes(fieldName)}
                        onChange={(event) => {
                          setSelectedFields((current) =>
                            event.target.checked
                              ? [...current, fieldName]
                              : current.filter((field) => field !== fieldName),
                          );
                        }}
                      />
                      <span>{humanizeStatus(fieldName)}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <label className={styles.checkboxLabel}>
                <input
                  type="checkbox"
                  checked={includeLineItems}
                  onChange={(event) => setIncludeLineItems(event.target.checked)}
                />
                <span>Extract detailed line items (quantity, unit price, amount)</span>
              </label>
              <label className={styles.fileDrop}>
                <span>Source files</span>
                <input
                  type="file"
                  multiple
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    setSelectedFiles(Array.from(event.target.files ?? []));
                    setBulkProgress(null);
                  }}
                />
                <strong>
                  {selectedFiles.length === 0
                    ? "No files selected"
                    : selectedFiles.length === 1
                      ? selectedFiles[0].name
                      : `${selectedFiles.length} files selected`}
                </strong>
              </label>
              <button type="submit" disabled={busy || !selectedCategory.trim()}>
                {selectedFiles.length > 1 ? "Bulk upload and process" : "Upload and process"}
              </button>
              {bulkProgress ? (
                <div className={styles.progressWrap}>
                  <progress
                    className={styles.progressBar}
                    max={bulkProgress.total}
                    value={bulkProgress.completed}
                  />
                  <small className={styles.progressMeta}>
                    {bulkProgress.completed}/{bulkProgress.total} completed · ok {bulkProgress.succeeded} · failed{" "}
                    {bulkProgress.failed}
                  </small>
                </div>
              ) : null}
            </form>
          </article>

          <article className={styles.panel}>
            <div className={styles.sectionHeader}>
              <div>
                <p className={styles.eyebrow}>Exceptions</p>
                <h2>Review queue</h2>
              </div>
              <span className={styles.badge}>{reviewQueue.length}</span>
            </div>
            <div className={styles.reviewList}>
              {reviewQueue.length === 0 ? (
                <p className={styles.emptyState}>No items require review right now.</p>
              ) : (
                reviewQueue.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setSelectedId(item.id);
                      setSelectedCategory(item.category);
                    }}
                    className={`${styles.reviewCard} ${selectedId === item.id ? styles.reviewCardActive : ""}`}
                  >
                    <div>
                      <strong>{item.filename}</strong>
                      <span>{item.anomaly_flags[0]?.message ?? "Manual review required"}</span>
                    </div>
                    <small>{formatTimestamp(item.updated_at)}</small>
                  </button>
                ))
              )}
            </div>
          </article>
          </div>
          <div className={styles.column}>
          <article className={styles.panel}>
            <div className={styles.sectionHeader}>
              <div>
                <p className={styles.eyebrow}>Case detail</p>
                <h2>{selectedItem ? selectedItem.filename : "Select a work item"}</h2>
              </div>
            </div>
            {selectedItem ? (
              <>
                <div className={styles.stageRail}>
                  {stageLabels.map((stage) => (
                    <div key={stage.key} className={`${styles.stage} ${styles[stageState(selectedItem, stage.key)]}`}>
                      <span>{stage.label}</span>
                    </div>
                  ))}
                </div>

                <div className={styles.detailGrid}>
                  <div>
                    <span>State</span>
                    <strong>{humanizeStatus(selectedItem.state)}</strong>
                  </div>
                  <div>
                    <span>Category</span>
                    <strong>{humanizeStatus(selectedItem.category)}</strong>
                  </div>
                  <div>
                    <span>OCR</span>
                    <strong>{humanizeStatus(selectedItem.ocr_backend)}</strong>
                  </div>
                  <div>
                    <span>Extraction</span>
                    <strong>{humanizeStatus(selectedItem.extraction_status)}</strong>
                  </div>
                  <div>
                    <span>Updated</span>
                    <strong>{formatTimestamp(selectedItem.updated_at)}</strong>
                  </div>
                </div>

                <div className={styles.actionBar}>
                  {selectedItem.extraction_status !== "succeeded" ? (
                    <button type="button" disabled={busy} onClick={() => void handleExtract()}>
                      Re-run extraction
                    </button>
                  ) : null}
                  {selectedItem.extraction_status === "succeeded" && selectedItem.validation_status === "pending" ? (
                    <button type="button" disabled={busy} onClick={() => void handleValidate()}>
                      Validate and auto-export
                    </button>
                  ) : null}
                  {selectedItem.review_status === "queued" || selectedItem.state === "needs_review" ? (
                    <>
                      <button type="button" disabled={busy} onClick={() => void handleReview("approve")}>
                        Approve and export
                      </button>
                      <button type="button" className={styles.rejectButton} disabled={busy} onClick={() => void handleReview("reject")}>
                        Reject
                      </button>
                    </>
                  ) : null}
                </div>

                <section className={styles.infoBlock}>
                  <div className={styles.blockHeader}>
                    <h3>Source document</h3>
                    <button type="button" className={styles.secondaryButton} onClick={() => setPreviewOpen(true)}>
                      Preview
                    </button>
                  </div>
                  <p>{selectedItem.filename}</p>
                </section>

                {selectedItem.exported_artifact ? (
                  <section className={styles.infoBlock}>
                    <div className={styles.blockHeader}>
                      <h3>Export artifact</h3>
                      <span>{selectedItem.exported_artifact.format.toUpperCase()}</span>
                    </div>
                    <p>{selectedItem.exported_artifact.filename}</p>
                  </section>
                ) : null}

                {selectedItem.anomaly_flags.length > 0 ? (
                  <section className={styles.infoBlock}>
                    <div className={styles.blockHeader}>
                      <h3>Validation findings</h3>
                      <span>{selectedItem.anomaly_flags.length}</span>
                    </div>
                    <div className={styles.findings}>
                      {selectedItem.anomaly_flags.map((flag) => (
                        <article key={flag.code} className={styles.finding}>
                          <strong>{flag.severity}</strong>
                          <p>{flag.message}</p>
                        </article>
                      ))}
                    </div>
                  </section>
                ) : null}

                {(selectedItem.review_status === "queued" || selectedItem.state === "needs_review") ? (
                  <section className={styles.infoBlock}>
                    <div className={styles.blockHeader}>
                      <h3>Manual review editor</h3>
                      <span>editable</span>
                    </div>
                    <label className={styles.reviewLabel}>
                      Review notes
                      <textarea
                        className={styles.reviewTextarea}
                        value={reviewNotes}
                        onChange={(event) => setReviewNotes(event.target.value)}
                        placeholder="Explain what was corrected or why this is approved."
                      />
                    </label>
                    <label className={styles.reviewLabel}>
                      Extracted payload (JSON)
                      <textarea
                        className={styles.jsonEditor}
                        value={editedDataText}
                        onChange={(event) => setEditedDataText(event.target.value)}
                      />
                    </label>
                  </section>
                ) : null}

                <section className={styles.infoBlock}>
                  <div className={styles.blockHeader}>
                    <h3>Structured payload</h3>
                    <span>{humanizeStatus(selectedItem.extraction_backend)}</span>
                  </div>
                  <pre>{JSON.stringify(selectedItem.extracted_data ?? {}, null, 2)}</pre>
                </section>

                <section className={styles.infoBlock}>
                  <div className={styles.blockHeader}>
                    <h3>LLM feedback</h3>
                    <span>{humanizeStatus(selectedItem.extraction_backend)}</span>
                  </div>
                  <p>
                    {typeof selectedItem.extracted_data?.explanation === "string" && selectedItem.extracted_data.explanation
                      ? selectedItem.extracted_data.explanation
                      : "No explanation returned by extraction backend."}
                  </p>
                </section>

                <section className={styles.infoBlock}>
                  <div className={styles.blockHeader}>
                    <h3>Audit timeline</h3>
                    <span>{auditEvents.length} events</span>
                  </div>
                  <div className={styles.timeline}>
                    {auditEvents.length === 0 ? (
                      <p className={styles.emptyState}>No audit events yet.</p>
                    ) : (
                      auditEvents.map((event) => (
                        <article key={`${event.timestamp}_${event.event_type}`} className={styles.timelineItem}>
                          <div>
                            <strong>{humanizeStatus(event.event_type)}</strong>
                            <span>{event.actor}</span>
                          </div>
                          <small>{formatTimestamp(event.timestamp)}</small>
                        </article>
                      ))
                    )}
                  </div>
                </section>
              </>
            ) : (
              <p className={styles.emptyState}>Select a work item to inspect its routing and history.</p>
            )}
          </article>

          <article className={styles.panel}>
            <div className={styles.sectionHeader}>
              <div>
                <p className={styles.eyebrow}>Observability</p>
                <h2>Tracking</h2>
              </div>
            </div>
            {observability ? (
              <div className={styles.detailGrid}>
                <div>
                  <span>Tracker</span>
                  <strong>{observability.backend}</strong>
                </div>
                <div>
                  <span>Audit store</span>
                  <strong>{observability.audit_backend}</strong>
                </div>
                <div>
                  <span>Experiment</span>
                  <strong>{observability.experiment_name ?? "default"}</strong>
                </div>
                <div>
                  <span>URI</span>
                  <strong>{observability.tracking_uri ?? observability.path ?? "local"}</strong>
                </div>
              </div>
            ) : (
              <p className={styles.emptyState}>Observability status unavailable.</p>
            )}
          </article>
          </div>
        </div>
      </section>

      {previewOpen && selectedItem ? (
        <div className={styles.previewOverlay} onClick={() => setPreviewOpen(false)}>
          <div className={styles.previewModal} onClick={(event) => event.stopPropagation()}>
            <div className={styles.blockHeader}>
              <h3>{selectedItem.filename}</h3>
              <button type="button" className={styles.secondaryButton} onClick={() => setPreviewOpen(false)}>
                Close
              </button>
            </div>
            {selectedItem.content_type.startsWith("image/") ? (
              <img
                src={`${API_BASE_URL}/api/v1/documents/${selectedItem.document_id}/download`}
                alt={selectedItem.filename}
                className={styles.previewImage}
              />
            ) : (
              <iframe
                src={`${API_BASE_URL}/api/v1/documents/${selectedItem.document_id}/download`}
                title={selectedItem.filename}
                className={styles.previewFrame}
              />
            )}
          </div>
        </div>
      ) : null}
    </main>
  );
}
