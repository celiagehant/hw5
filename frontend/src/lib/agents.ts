// Visual identity for each actor that can appear in the audit trail, and the
// presentation of each backend event type. Everything here keys off fields the
// backend actually sends (`agent`, `event_type`), never off free text.

import type { IconName } from "../components/Icon";

export interface AgentIdentity {
  id: string;
  name: string;
  role: string;
  initials: string;
  color: string;
  icon: IconName;
}

export const AGENTS: Record<string, AgentIdentity> = {
  boss: { id: "boss", name: "Boss", role: "Operations Manager", initials: "BO", color: "#00356b", icon: "compass" },
  inventory: { id: "inventory", name: "Inventory", role: "Inventory Manager", initials: "IN", color: "#1d6f6a", icon: "box" },
  accounting: { id: "accounting", name: "Accounting", role: "Accounting Manager", initials: "AC", color: "#6a3d78", icon: "ledger" },
  facilities: { id: "facilities", name: "Facilities", role: "Facilities Manager", initials: "FA", color: "#8a6212", icon: "building" },
  customer_service: { id: "customer_service", name: "Customer Service", role: "Customer Service Manager", initials: "CS", color: "#4c7326", icon: "chat" },
};

export const TEAM_ORDER = ["boss", "inventory", "accounting", "facilities", "customer_service"] as const;

const HUMAN: AgentIdentity = { id: "human_operator", name: "You", role: "Human operator", initials: "OP", color: "#2b3440", icon: "user" };
const DESK: AgentIdentity = { id: "orchestrator", name: "Desk", role: "Orchestrator", initials: "DK", color: "#6b7480", icon: "desk" };

export function agentIdentity(agent: string | null | undefined): AgentIdentity {
  if (!agent) return DESK;
  if (agent === "human_operator") return HUMAN;
  return (
    AGENTS[agent] ?? {
      id: agent,
      name: agent.replace(/_/g, " "),
      role: "Agent",
      initials: agent.slice(0, 2).toUpperCase(),
      color: "#6b7480",
      icon: "desk",
    }
  );
}

export type Tone = "neutral" | "progress" | "success" | "attention" | "danger";

export interface EventKind {
  label: string;
  tone: Tone;
  icon: IconName;
}

const KINDS: Record<string, EventKind> = {
  run_started: { label: "Run started", tone: "progress", icon: "play" },
  ticket_loaded: { label: "Ticket loaded", tone: "neutral", icon: "ticket" },
  state_transition: { label: "Status", tone: "neutral", icon: "flag" },
  agent_started: { label: "Investigating", tone: "progress", icon: "search" },
  mcp_tool_call: { label: "Tool call", tone: "neutral", icon: "wrench" },
  mcp_tool_error: { label: "Tool error", tone: "danger", icon: "alert" },
  delegation_requested: { label: "Delegation", tone: "progress", icon: "arrow" },
  delegation_completed: { label: "Handoff returned", tone: "neutral", icon: "return" },
  delegation_refused: { label: "Delegation refused", tone: "attention", icon: "stop" },
  guardrail_applied: { label: "Guardrail", tone: "attention", icon: "shield" },
  limit_reached: { label: "Limit reached", tone: "danger", icon: "stop" },
  agent_retry: { label: "Retry", tone: "attention", icon: "refresh" },
  agent_failed: { label: "Agent failed", tone: "danger", icon: "alert" },
  run_completed: { label: "Run finished", tone: "success", icon: "check" },
  run_failed: { label: "Run failed", tone: "danger", icon: "alert" },
  proposals_recorded: { label: "Proposals recorded", tone: "neutral", icon: "file" },
  payment_executed: { label: "Payment executed", tone: "success", icon: "coin" },
  purchase_approved: { label: "Purchase approved", tone: "success", icon: "check" },
  approval_refused: { label: "Approval refused", tone: "danger", icon: "stop" },
  discount_approved: { label: "Discount approved", tone: "success", icon: "check" },
  proposal_declined: { label: "Declined by you", tone: "neutral", icon: "x" },
  database_reset: { label: "Database reset", tone: "attention", icon: "refresh" },
};

/** How to present an event. agent_completed is a "Decision" when the Boss sent it. */
export function eventKind(eventType: string, agent: string | null): EventKind {
  if (eventType === "agent_completed") {
    return agent === "boss"
      ? { label: "Decision", tone: "success", icon: "gavel" }
      : { label: "Finding", tone: "success", icon: "spark" };
  }
  return KINDS[eventType] ?? { label: eventType.replace(/_/g, " "), tone: "neutral", icon: "dot" };
}
