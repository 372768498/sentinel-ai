import { appEnv, assertServerEnv } from "@/lib/env";

export type AnalyzeMode = "basic" | "deep";

export type WorkerAnalyzePayload = {
  historyId: string;
  ticker: string;
  email: string;
  requestedMode: AnalyzeMode;
  deepMode?: string;
  callbackUrl: string;
  callbackSecret: string;
};

export type WorkerAnalyzeResponse = {
  jobId: string;
  status: "queued" | "running";
  eventsUrl: string;
  pollUrl: string;
};

export async function createWorkerJob(payload: WorkerAnalyzePayload): Promise<WorkerAnalyzeResponse> {
  const response = await fetch(`${appEnv.workerApiBaseUrl}/api/analyze`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-internal-token": assertServerEnv("WORKER_INTERNAL_TOKEN", appEnv.workerInternalToken)
    },
    body: JSON.stringify(payload),
    cache: "no-store"
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Worker analyze request failed: ${response.status} ${message}`);
  }

  return response.json();
}
