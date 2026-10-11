// Small reusable pieces: status pills, agent monograms, spinners, inline notices.

import type { ReactNode } from "react";
import { agentIdentity, type Tone } from "../lib/agents";
import { Icon, type IconName } from "./Icon";

export function Pill({
  tone,
  children,
  icon,
  live = false,
}: {
  tone: Tone;
  children: ReactNode;
  icon?: IconName;
  live?: boolean;
}) {
  return (
    <span className={`pill pill--${tone}`}>
      {live ? <span className="live-dot" aria-hidden /> : icon ? <Icon name={icon} size={13} /> : null}
      {children}
    </span>
  );
}

export function AgentMark({ agent, size = "md" }: { agent: string | null; size?: "sm" | "md" | "lg" }) {
  const a = agentIdentity(agent);
  return (
    <span
      className={`agent-mark agent-mark--${size}`}
      style={{ ["--agent" as string]: a.color }}
      title={`${a.name} · ${a.role}`}
      aria-label={`${a.name}, ${a.role}`}
      role="img"
    >
      {a.initials}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner" role="status" aria-label={label ?? "Loading"}>
      <span className="spinner__ring" aria-hidden />
    </span>
  );
}

export function Notice({
  tone,
  title,
  children,
  action,
}: {
  tone: Tone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  const icon: IconName =
    tone === "danger" ? "alert" : tone === "success" ? "check" : tone === "attention" ? "flag" : "clock";
  return (
    <div className={`notice notice--${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <Icon name={icon} size={16} className="notice__icon" />
      <div className="notice__body">
        {title && <strong className="notice__title">{title}</strong>}
        {children && <div className="notice__text">{children}</div>}
      </div>
      {action && <div className="notice__action">{action}</div>}
    </div>
  );
}

export function SectionTitle({ kicker, children, aside }: { kicker?: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="section-title">
      <div>
        {kicker && <div className="kicker">{kicker}</div>}
        <h2 className="serif">{children}</h2>
      </div>
      {aside && <div className="section-title__aside">{aside}</div>}
    </div>
  );
}
