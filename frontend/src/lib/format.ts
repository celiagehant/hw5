import type { RunSummary, Ticket, WorkflowStatus } from "../api/types";
import type { Tone } from "./agents";

export function money(amount: number, currency = "USD"): string {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

export function time(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function timeShort(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function dateLong(isoDate: string | null | undefined): string {
  if (!isoDate) return "";
  const d = new Date(`${isoDate.slice(0, 10)}T12:00:00`);
  return Number.isNaN(d.getTime())
    ? isoDate
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "";
  const s = value.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function elapsed(fromIso: string, toIso?: string | null): string {
  const from = new Date(fromIso).getTime();
  const to = toIso ? new Date(toIso).getTime() : Date.now();
  if (Number.isNaN(from) || Number.isNaN(to)) return "";
  const s = Math.max(0, Math.round((to - from) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

export const WORKFLOW_LABEL: Record<WorkflowStatus, string> = {
  received: "Received",
  in_progress: "In progress",
  awaiting_human_approval: "Awaiting approval",
  blocked: "Blocked",
  needs_clarification: "Needs clarification",
  escalated: "Escalated to a human",
  resolved: "Resolved by agents",
  limit_reached: "Stopped at a limit",
  failed: "Run failed",
};

export const WORKFLOW_TONE: Record<WorkflowStatus, Tone> = {
  received: "neutral",
  in_progress: "progress",
  awaiting_human_approval: "attention",
  blocked: "danger",
  needs_clarification: "attention",
  escalated: "attention",
  resolved: "success",
  limit_reached: "danger",
  failed: "danger",
};

export type DeskState = "running" | "resolved" | "attention" | "blocked" | "failed" | "open";

export interface TicketState {
  key: DeskState;
  label: string;
  tone: Tone;
}

/**
 * The ticket's state on the desk. "Resolved" comes only from the persisted
 * tickets.status; the rest come from the active run or the last recorded run.
 */
export function ticketState(ticket: Ticket, sessionRun?: RunSummary | null): TicketState {
  if (ticket.active_run?.state === "running" || sessionRun?.state === "running") {
    return { key: "running", label: "Agents working", tone: "progress" };
  }
  if (ticket.status.toLowerCase() === "resolved") {
    return { key: "resolved", label: "Resolved", tone: "success" };
  }
  if (sessionRun?.state === "failed") {
    return { key: "failed", label: "Run failed", tone: "danger" };
  }
  const last = ticket.latest_run?.run_status;
  switch (last) {
    case "awaiting_human_approval":
      return { key: "attention", label: "Awaiting approval", tone: "attention" };
    case "escalated":
      return { key: "attention", label: "Escalated", tone: "attention" };
    case "needs_clarification":
      return { key: "attention", label: "Needs clarification", tone: "attention" };
    case "blocked":
      return { key: "blocked", label: "Blocked", tone: "danger" };
    case "limit_reached":
    case "failed":
      return { key: "failed", label: WORKFLOW_LABEL[last], tone: "danger" };
    default:
      return { key: "open", label: last ? "Open" : "Open · not yet run", tone: "neutral" };
  }
}

export function ticketTypeLabel(type: string): string {
  return humanize(type);
}
