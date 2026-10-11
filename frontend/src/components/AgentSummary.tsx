import type { DashboardEvent, TicketRunResult } from "../api/types";
import { AGENTS, TEAM_ORDER } from "../lib/agents";
import { humanize } from "../lib/format";
import { Icon } from "./Icon";
import { AgentMark, Pill, SectionTitle } from "./ui";

interface Contribution {
  id: string;
  calls: number;
  outcome: string | null;
  summary: string | null;
  findings: string[];
  blockers: string[];
  tools: string[];
  delegatedTo: string[];
  askedBy: string[];
}

const OUTCOME_TONE: Record<string, "success" | "attention" | "danger" | "neutral"> = {
  completed: "success",
  resolved: "success",
  awaiting_human_approval: "attention",
  needs_information: "attention",
  needs_clarification: "attention",
  escalate: "attention",
  escalated: "attention",
  blocked: "danger",
  failed: "danger",
};

function asList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === "string" && value) return [value];
  return [];
}

/** Builds each agent's contribution from the run result when the backend still
 *  holds it, otherwise from the run's recorded events only. */
function contributions(result: TicketRunResult | undefined, events: DashboardEvent[]): Contribution[] {
  const out = new Map<string, Contribution>();
  const get = (id: string) => {
    if (!out.has(id)) {
      out.set(id, { id, calls: 0, outcome: null, summary: null, findings: [], blockers: [], tools: [], delegatedTo: [], askedBy: [] });
    }
    return out.get(id)!;
  };
  const addUnique = (list: string[], v: string) => !list.includes(v) && list.push(v);

  for (const e of events) {
    if (!e.agent || !(e.agent in AGENTS)) continue;
    const c = get(e.agent);
    if (e.event_type === "agent_started") c.calls += 1;
    if (e.event_type === "mcp_tool_call" && e.tool?.name) addUnique(c.tools, e.tool.name);
    if (e.event_type === "delegation_requested" && e.delegation_target) {
      addUnique(c.delegatedTo, e.delegation_target);
      addUnique(get(e.delegation_target).askedBy, e.agent);
    }
    if (e.event_type === "agent_completed") {
      c.outcome = e.status ?? c.outcome;
      const f = asList(e.findings);
      if (f.length) {
        c.findings = f;
        c.summary = f[0];
      }
    }
  }

  // Richer, full-length text from the run result, when available.
  for (const r of result?.specialist_reports ?? []) {
    const c = get(r.agent);
    c.outcome = r.report.outcome;
    c.summary = r.report.summary;
    c.findings = (r.report.findings ?? []).map((f) => f.summary);
    c.blockers = r.report.blockers ?? [];
  }
  if (result?.decision) {
    const c = get("boss");
    c.outcome = result.decision.proposed_status;
    c.summary = result.decision.decision;
    c.findings = [];
    c.blockers = result.decision.blockers ?? [];
  }
  for (const a of result?.agent_runs ?? []) {
    const c = get(a.agent);
    c.calls = Math.max(c.calls, (result?.agent_runs ?? []).filter((x) => x.agent === a.agent).length);
  }
  return TEAM_ORDER.filter((id) => out.has(id)).map((id) => out.get(id)!);
}

export function AgentSummary({
  result,
  runEvents,
  hasRun,
}: {
  result: TicketRunResult | undefined;
  runEvents: DashboardEvent[];
  hasRun: boolean;
}) {
  if (!hasRun) return null;
  const list = contributions(result, runEvents);
  const involved = new Set(list.map((c) => c.id));

  return (
    <section className="panel">
      <SectionTitle kicker="Who did what">Agent contributions</SectionTitle>

      <ol className="team" aria-label="Agents involved in this run">
        {TEAM_ORDER.map((id) => (
          <li key={id} className={involved.has(id) ? "team__member team__member--on" : "team__member"}>
            <AgentMark agent={id} size="sm" />
            <span>{AGENTS[id].name}</span>
            {!involved.has(id) && <span className="team__off">not called</span>}
          </li>
        ))}
      </ol>

      {list.length === 0 ? (
        <p className="muted">Contributions appear here as agents report back.</p>
      ) : (
        <div className="contribs">
          {list.map((c) => {
            const a = AGENTS[c.id];
            return (
              <article key={c.id} className="contrib" style={{ ["--agent" as string]: a.color }}>
                <header className="contrib__head">
                  <AgentMark agent={c.id} />
                  <div>
                    <div className="contrib__name">{a.name}</div>
                    <div className="contrib__role">{a.role}</div>
                  </div>
                  {c.outcome ? (
                    <Pill tone={OUTCOME_TONE[c.outcome] ?? "neutral"}>{humanize(c.outcome)}</Pill>
                  ) : (
                    <Pill tone="progress" live>
                      Working
                    </Pill>
                  )}
                </header>
                {c.summary && <p className="contrib__summary">{c.summary}</p>}
                {c.findings.length > 1 && (
                  <ul className="contrib__findings">
                    {c.findings.slice(c.summary === c.findings[0] ? 1 : 0, 4).map((f, i) => (
                      <li key={i}>{f}</li>
                    ))}
                  </ul>
                )}
                {c.blockers.length > 0 && (
                  <ul className="contrib__blockers">
                    {c.blockers.map((b, i) => (
                      <li key={i}>
                        <Icon name="stop" size={12} /> {b}
                      </li>
                    ))}
                  </ul>
                )}
                <footer className="contrib__foot">
                  {c.askedBy.length > 0 && <span>Asked by {c.askedBy.map((x) => AGENTS[x]?.name ?? x).join(", ")}</span>}
                  {c.delegatedTo.length > 0 && (
                    <span>
                      <Icon name="arrow" size={12} /> {c.delegatedTo.map((x) => AGENTS[x]?.name ?? x).join(", ")}
                    </span>
                  )}
                  {c.tools.length > 0 && (
                    <span className="contrib__tools">
                      <Icon name="wrench" size={12} /> {c.tools.join(", ")}
                    </span>
                  )}
                  {c.calls > 1 && <span>{c.calls} runs</span>}
                </footer>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
