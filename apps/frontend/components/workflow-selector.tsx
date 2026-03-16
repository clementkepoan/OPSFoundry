"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { API_BASE_URL, apiGet } from "../lib/api";
import styles from "./workflow-selector.module.css";

type Workflow = {
  name: string;
  description: string;
  states: string[];
};

export function WorkflowSelector() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [statusMessage, setStatusMessage] = useState("Loading available workflows...");

  useEffect(() => {
    void apiGet<Workflow[]>("/api/v1/workflows").then(
      (data) => {
        setWorkflows(data);
        setStatusMessage("Choose a workflow to open its operations HUD.");
      },
      (error: Error) => setStatusMessage(error.message),
    );
  }, []);

  return (
    <main className={styles.shell}>
      <section className={styles.hero}>
        <div className={styles.copy}>
          <p className={styles.kicker}>OPSFoundry</p>
          <h1>Select a workflow before entering the operations HUD.</h1>
          <p className={styles.lead}>
            Each workflow gets its own dedicated console. Start here, pick the workflow you want to
            operate, and the app will take you into that workflow’s live queue and routing view.
          </p>
        </div>
        <div className={styles.endpointCard}>
          <span>API endpoint</span>
          <code>{API_BASE_URL}/api/v1/workflows</code>
          <p>{statusMessage}</p>
        </div>
      </section>

      <section className={styles.grid}>
        {workflows.map((workflow) => (
          <button
            key={workflow.name}
            type="button"
            className={styles.card}
            onClick={() => router.push(`/workflows/${encodeURIComponent(workflow.name)}`)}
          >
            <div className={styles.cardTop}>
              <p>{workflow.name}</p>
              <span>{workflow.states.length} states</span>
            </div>
            <h2>{workflow.description}</h2>
            <div className={styles.flow}>
              {workflow.states.slice(0, 5).map((state) => (
                <span key={state}>{state.replace(/_/g, " ")}</span>
              ))}
            </div>
            <strong>Open workflow HUD</strong>
          </button>
        ))}
      </section>
    </main>
  );
}
