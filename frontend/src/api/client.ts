// The single place that knows where the backend lives and how to talk to it.

import type {
  ApiErrorBody,
  ApprovalRequest,
  ApprovalResult,
  Balance,
  DeclineResult,
  EventsResponse,
  HealthResponse,
  ProposalsResponse,
  ResetResult,
  RunDetail,
  StartRunResponse,
  TicketDetail,
  TicketsResponse,
} from "./types";

export const API_BASE: string = (
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000"
).replace(/\/$/, "");

const TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  /** HTTP status, or 0 when the backend could not be reached. */
  readonly status: number;
  /** Backend error code (e.g. "insufficient_funds"), or a client-side code. */
  readonly code: string;
  readonly body?: unknown;

  constructor(status: number, code: string, message: string, body?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.body = body;
  }

  get isNetwork(): boolean {
    return this.status === 0;
  }
}

function messageFrom(status: number, body: unknown): { code: string; message: string } {
  if (body && typeof body === "object") {
    const b = body as Partial<ApiErrorBody> & { detail?: unknown };
    if (typeof b.message === "string") {
      return { code: typeof b.error === "string" ? b.error : `http_${status}`, message: b.message };
    }
    // FastAPI request-validation errors: {"detail": [{"msg": ...}, ...]}
    if (Array.isArray(b.detail)) {
      const msgs = b.detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : ""))
        .filter(Boolean);
      return { code: "validation_error", message: msgs.join("; ") || "The request was invalid." };
    }
    if (typeof b.detail === "string") return { code: `http_${status}`, message: b.detail };
  }
  return { code: `http_${status}`, message: `The backend answered with HTTP ${status}.` };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch (err) {
    const timedOut = err instanceof DOMException && err.name === "AbortError";
    throw new ApiError(
      0,
      timedOut ? "timeout" : "network",
      timedOut
        ? "The backend did not answer in time."
        : `Cannot reach the backend at ${API_BASE}. Is uvicorn running?`,
    );
  } finally {
    window.clearTimeout(timer);
  }

  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    const { code, message } = messageFrom(res.status, body);
    throw new ApiError(res.status, code, message, body);
  }
  return body as T;
}

function query(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  tickets: () => request<TicketsResponse>("/api/tickets"),
  ticket: (id: number) => request<TicketDetail>(`/api/tickets/${id}`),
  startRun: (id: number) => request<StartRunResponse>(`/api/tickets/${id}/run`, { method: "POST" }),
  run: (runId: string) => request<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`),
  events: (p: { ticket_id?: number; run_id?: string; after?: string | null; limit?: number }) =>
    request<EventsResponse>(`/api/events${query(p)}`),
  proposals: (ticketId?: number) =>
    request<ProposalsResponse>(`/api/proposals${query({ ticket_id: ticketId })}`),
  approve: (proposalId: number, body: ApprovalRequest) =>
    request<ApprovalResult>(`/api/proposals/${proposalId}/approve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  decline: (proposalId: number, body: { declined_by: string; reason: string }) =>
    request<DeclineResult>(`/api/proposals/${proposalId}/decline`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  balance: () => request<Balance>("/api/cash/checking"),
  reset: () =>
    request<ResetResult>("/api/reset", { method: "POST", body: JSON.stringify({ confirm: "RESET" }) }),
};
