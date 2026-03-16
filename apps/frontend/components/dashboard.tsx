"use client";

import { ChangeEvent, FormEvent, startTransition, useEffect, useMemo, useState } from "react";

import { API_BASE_URL, apiGet, apiPost } from "../lib/api";
import styles from "./dashboard.module.css";

type WorkflowMetadata = {
  name: string;
  description: string;
  states: string[];
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
  state: string;
  filename: string;
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
  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [reviewQueue, setReviewQueue] = useState<WorkItem[]>([]);
  const [observability, setObservability] = useState<ObservabilityStatus | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Loading workflow HUD...");

  const selectedItem = useMemo(
    () => workItems.find((item) => item.id === selectedId) ?? reviewQueue.find((item) => item.id === selectedId) ?? null,
    [reviewQueue, selectedId, workItems],
  );

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
    if (!selectedFile) {
      setStatusMessage("Select a source file before uploading.");
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);

    await performAction<UploadReceipt>(
      `Uploading ${selectedFile.name}`,
      () =>
        apiPost<UploadReceipt>(
          `/api/v1/workflows/${encodeURIComponent(workflowName)}/documents`,
          formData,
          idempotencyHeader(
            `upload:${workflowName}:${selectedFile.name}:${selectedFile.size}:${selectedFile.lastModified}`,
          ),
        ),
      (receipt) => {
        setSelectedFile(null);
        return {
          focusId: receipt.work_item.id,
          message:
            receipt.extraction.status === "succeeded"
              ? `Uploaded and extracted ${selectedFile.name}. Validate to route it.`
              : `Uploaded ${selectedFile.name}, but extraction needs attention.`,
        };
      },
    );
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
    await performAction<ReviewResponse>(
      `${action === "approve" ? "Approving" : "Rejecting"} ${selectedItem.filename}`,
      () =>
        apiPost<ReviewResponse>(`/api/v1/work-items/${selectedItem.id}/review`, {
          action,
          review_notes:
            action === "approve"
              ? "Approved from the operations console."
              : "Rejected from the operations console.",
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
        <div className={styles.sidebar}>
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
              <label className={styles.fileDrop}>
                <span>Source file</span>
                <input
                  type="file"
                  onChange={(event: ChangeEvent<HTMLInputElement>) =>
                    setSelectedFile(event.target.files?.[0] ?? null)
                  }
                />
                <strong>{selectedFile?.name ?? "No file selected"}</strong>
              </label>
              <button type="submit" disabled={busy}>
                Upload and extract
              </button>
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
                    onClick={() => setSelectedId(item.id)}
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

        <section className={styles.workspace}>
          <article className={styles.panel}>
            <div className={styles.sectionHeader}>
              <div>
                <p className={styles.eyebrow}>Portfolio</p>
                <h2>Work item ledger</h2>
              </div>
              <button type="button" className={styles.secondaryButton} onClick={() => void refreshAll(selectedId)}>
                Refresh
              </button>
            </div>
            <div className={styles.ledger}>
              {workItems.length === 0 ? (
                <p className={styles.emptyState}>No work items for this workflow yet.</p>
              ) : (
                workItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    className={`${styles.ledgerCard} ${styles[itemTone(item)]} ${selectedId === item.id ? styles.activeCard : ""}`}
                  >
                    <div className={styles.ledgerTop}>
                      <div>
                        <strong>{item.filename}</strong>
                        <span>{item.id.slice(0, 8)} · {item.workflow_name}</span>
                      </div>
                      <span className={styles.stateChip}>{humanizeStatus(item.state)}</span>
                    </div>
                    <div className={styles.ledgerMeta}>
                      <span>OCR: {humanizeStatus(item.ocr_backend)}</span>
                      <span>Extraction: {humanizeStatus(item.extraction_status)}</span>
                      <span>Validation: {humanizeStatus(item.validation_status)}</span>
                      <span>Review: {humanizeStatus(item.review_status)}</span>
                    </div>
                    <div className={styles.ledgerFooter}>
                      <span>{nextAction(item)}</span>
                      <small>{formatTimestamp(item.updated_at)}</small>
                    </div>
                  </button>
                ))
              )}
            </div>
          </article>
        </section>

        <aside className={styles.detailRail}>
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
                  {selectedItem.extraction_status === "succeeded" && selectedItem.validation_status !== "passed" && selectedItem.review_status !== "queued" && selectedItem.state !== "needs_review" ? (
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

                <section className={styles.infoBlock}>
                  <div className={styles.blockHeader}>
                    <h3>Structured payload</h3>
                    <span>{humanizeStatus(selectedItem.extraction_backend)}</span>
                  </div>
                  <pre>{JSON.stringify(selectedItem.extracted_data ?? {}, null, 2)}</pre>
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
        </aside>
      </section>
    </main>
  );
}
