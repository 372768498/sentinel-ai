import crypto from "node:crypto";

import { appEnv } from "@/lib/env";

type AlertSeverity = "high" | "medium";

export type OpsAlertInput = {
  title: string;
  severity: AlertSeverity;
  details: Record<string, unknown>;
};

function constantTimeMatch(expected: string, candidate: string) {
  const expectedBuffer = Buffer.from(expected, "utf8");
  const candidateBuffer = Buffer.from(candidate, "utf8");

  if (expectedBuffer.length !== candidateBuffer.length) {
    return false;
  }

  return crypto.timingSafeEqual(expectedBuffer, candidateBuffer);
}

export function isAuthorizedAdminRequest(request: Request) {
  const secret = appEnv.adminApiKey;

  if (!secret) {
    return false;
  }

  const bearerToken = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "").trim();
  const adminHeader = request.headers.get("x-admin-key")?.trim();
  const candidate = bearerToken || adminHeader;

  if (!candidate) {
    return false;
  }

  return constantTimeMatch(secret, candidate);
}

export function requireAdminRequest(request: Request) {
  return isAuthorizedAdminRequest(request)
    ? null
    : Response.json({ error: "Unauthorized admin request" }, { status: 401 });
}

export async function sendOpsAlert(input: OpsAlertInput) {
  const payload = {
    source: "sentinel-ai",
    timestamp: new Date().toISOString(),
    ...input
  };

  console.error(`[OPS ALERT] ${input.title}`, payload.details);

  if (!appEnv.opsAlertWebhookUrl) {
    return { delivered: false };
  }

  const response = await fetch(appEnv.opsAlertWebhookUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`Ops alert webhook failed: ${response.status} ${await response.text()}`);
  }

  return { delivered: true };
}
