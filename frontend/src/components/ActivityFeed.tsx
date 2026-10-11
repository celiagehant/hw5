import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { DashboardEvent } from "../api/types";
import { agentIdentity, eventKind } from "../lib/agents";
import { humanize, time } from "../lib/format";
import { Icon } from "./Icon";
import { AgentMark, Notice, Pill, Spinner } from "./ui";

interface Props {
  ticketId: number;
  events: DashboardEvent[];
  loaded: boolean;
  error?: string;
  currentRunId: string | null;
  running: boolean;
  onRetry: () => void;
}

/** Index where the current run's activity starts (its run_started event). */
function currentRunStart(events: DashboardEvent[], runId: string | null): number {
  if (!runId) return events.length;
  const i = events.findIndex((e) => e.run_id === runId && e.event_type === "run_started");
  if (i >= 0) return i;
  const j = events.findIndex((e) => e.run_id === runId);
  return j >= 0 ? j : events.length;
}

export function ActivityFeed({ ticketId, events, loaded, error, currentRunId, running, onRetry }: Props) {
  const [showEarlier, setShowEarlier] = useState(false);
  const listRef = useRef<HTMLOListElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => setShowEarlier(false), [ticketId]);

  const start = currentRunStart(events, currentRunId);
  const visible = useMemo(() => (showEarlier ? events : events.slice(start)), [events, start, showEarlier]);
  const earlier = start;

  // Follow new events while the reader is at the bottom of the feed.
  useLayoutEffect(() => {
    const el = listRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [visible.length]);

  return (
    <aside className="feed" aria-label="Agent activity">
      <div className="feed__head">
        <div>
          <div className="kicker">Live activity · ticket {ticketId}</div>
          <h2 className="serif">Agent activity</h2>
        </div>
        {running ? (
          <Pill tone="progress" live>
            Live
          </Pill>
        ) : (
          <span className="feed__count">{visible.length} events</span>
        )}
      </div>

      {earlier > 0 && (
        <button type="button" className="feed__earlier" onClick={() => setShowEarlier((s) => !s)} aria-expanded={showEarlier}>
          {showEarlier ? "Hide earlier activity" : `Show ${earlier} earlier event${earlier > 1 ? "s" : ""} from past runs`}
        </button>
      )}

      {error && (
        <Notice
          tone="attention"
          title="Activity could not be refreshed"
          action={
            <button type="button" className="btn btn--small" onClick={onRetry}>
              Retry
            </button>
          }
        >
          {error}
        </Notice>
      )}

      {!loaded && !error ? (
        <div className="feed__empty">
          <Spinner label="Loading activity" /> Loading activity…
        </div>
      ) : visible.length === 0 ? (
        <div className="feed__empty">
          {running ? (
            <>
              <Spinner label="Waiting for events" /> The run has started; waiting for the first agent event…
            </>
          ) : currentRunId ? (
            "No events recorded for this run."
          ) : (
            "No activity since the last reset. Run the agent team to see each agent's work here."
          )}
        </div>
      ) : (
        <ol
          ref={listRef}
          className="timeline"
          aria-live="polite"
          aria-relevant="additions"
          onScroll={(e) => {
            const el = e.currentTarget;
            stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
          }}
        >
          {visible.map((e, i) => (
            <EventRow key={e.event_id} event={e} newRun={e.event_type === "run_started" && i > 0} />
          ))}
          {running && (
            <li className="timeline__pending">
              <span className="live-dot" aria-hidden /> Working…
            </li>
          )}
        </ol>
      )}
    </aside>
  );
}

function argText(args: Record<string, unknown> | null | undefined): string {
  if (!args) return "";
  return Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(", ");
}

function asList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((v) => (typeof v === "string" ? v : JSON.stringify(v)));
  if (typeof value === "string" && value) return [value];
  return [];
}

function EventRow({ event: e, newRun }: { event: DashboardEvent; newRun: boolean }) {
  const [open, setOpen] = useState(false);
  const kind = eventKind(e.event_type, e.agent);
  const who = agentIdentity(e.agent);
  // A returned handoff travels back from the delegate to the caller.
  const returning = e.event_type === "delegation_completed";
  const from = returning && e.delegation_target ? e.delegation_target : e.agent;
  const to = e.delegation_target ? (returning ? e.agent : e.delegation_target) : null;
  const findings = asList(e.findings);
  const recs = asList(e.recommendation);
  const records = e.tool?.record_ids ?? [];
  const hasDetails =
    findings.length > 0 || recs.length > 0 || records.length > 0 || Boolean(e.error) || Boolean(e.tool?.args) || Boolean(e.portkey_trace_id);

  return (
    <li
      className={`event event--${kind.tone} ${newRun ? "event--newrun" : ""}`}
      style={{ ["--agent" as string]: who.color }}
    >
      <span className="event__node" aria-hidden>
        <Icon name={kind.icon} size={12} />
      </span>
      <div className="event__body">
        <div className="event__top">
          <span className={`event__kind event__kind--${kind.tone}`}>{kind.label}</span>
          <span className="event__who">
            <AgentMark agent={from} size="sm" />
            <span className="event__name">{agentIdentity(from).name}</span>
            {to && (
              <>
                <Icon name="arrow" size={12} className="event__arrow" />
                <AgentMark agent={to} size="sm" />
                <span className="event__name">{agentIdentity(to).name}</span>
              </>
            )}
          </span>
          <time className="event__time" dateTime={e.timestamp}>
            {time(e.timestamp)}
          </time>
        </div>

        {e.tool && e.event_type !== "proposals_recorded" ? (
          <div className="event__tool">
            <code>
              {e.tool.name}({argText(e.tool.args)})
            </code>
            {e.tool.outcome && <span className="event__outcome">→ {e.tool.outcome}</span>}
          </div>
        ) : null}

        <p className={`event__desc ${open ? "event__desc--open" : ""}`}>{e.description || humanize(e.event_type)}</p>

        {(e.status || e.stop_reason) && (
          <div className="event__status">
            {e.status && <span className="tag">{humanize(e.status)}</span>}
            {e.stop_reason && <span className="event__reason">{e.stop_reason}</span>}
          </div>
        )}

        {hasDetails && (
          <button type="button" className="event__more" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            <Icon name="chevron" size={12} className={open ? "rot" : ""} /> {open ? "Less" : "Details"}
          </button>
        )}

        {open && (
          <div className="event__details">
            {findings.length > 0 && (
              <div>
                <h5>Findings</h5>
                <ul>
                  {findings.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
            )}
            {recs.length > 0 && (
              <div>
                <h5>Recommendation</h5>
                <ul>
                  {recs.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
            {records.length > 0 && (
              <div>
                <h5>Records returned</h5>
                <div className="event__records">
                  {records.map((r) => (
                    <code key={r}>{r}</code>
                  ))}
                </div>
              </div>
            )}
            {e.error && (
              <div>
                <h5>Error</h5>
                <p className="event__error">{e.error}</p>
              </div>
            )}
            <div className="event__trace">
              {who.role}
              {e.model ? ` · ${e.model}` : ""}
              {e.portkey_trace_id ? ` · trace ${e.portkey_trace_id}` : ""} · run {e.run_id}
            </div>
          </div>
        )}
      </div>
    </li>
  );
}
