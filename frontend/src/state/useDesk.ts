// All dashboard state and every API interaction live here; components only
// render what this hook exposes.
//
// Rules:
// - "Connected" is shown only after a real request has succeeded.
// - Events and run status are polled only while a run is active (every 2.5 s,
//   or 8 s while the backend is unreachable). When idle, a light health check
//   runs every 20 s so a dropped backend is noticed.
// - The balance is never computed here; it is always re-read from the backend.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type {
  ApprovalResult,
  Balance,
  DashboardEvent,
  DeclineResult,
  Proposal,
  ResetResult,
  RunDetail,
  Ticket,
  TicketDetail,
} from "../api/types";
import type { Tone } from "../lib/agents";
import { money, ticketState, WORKFLOW_LABEL } from "../lib/format";

export type Connection = "connecting" | "online" | "offline";

export interface TicketView {
  detail?: TicketDetail;
  detailError?: string;
  events: DashboardEvent[];
  eventsLoaded: boolean;
  eventsError?: string;
  proposals: Proposal[];
  proposalsLoaded: boolean;
  proposalsError?: string;
  /** The latest run this session has fetched from GET /api/runs/{id}. */
  run?: RunDetail;
  /** A run id the backend no longer holds in memory (e.g. after a restart). */
  runUnavailable?: string;
  runFeedback?: { tone: Tone; message: string };
}

export interface Toast {
  id: number;
  tone: Tone;
  title: string;
  message?: string;
}

export interface BalanceChange {
  from: number;
  to: number;
  at: number;
}

const EMPTY_VIEW: TicketView = { events: [], eventsLoaded: false, proposals: [], proposalsLoaded: false };

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}

function mergeEvents(current: DashboardEvent[], incoming: DashboardEvent[]): DashboardEvent[] {
  if (!incoming.length) return current;
  const byId = new Map(current.map((e) => [e.event_id, e]));
  for (const e of incoming) byId.set(e.event_id, e);
  // Stable sort keeps the backend's order for events with equal timestamps.
  return [...byId.values()].sort((a, b) => (a.timestamp < b.timestamp ? -1 : a.timestamp > b.timestamp ? 1 : 0));
}

export function useDesk() {
  const [connection, setConnection] = useState<Connection>("connecting");
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [ticketsError, setTicketsError] = useState<string | null>(null);
  const [shopDate, setShopDate] = useState<string | null>(null);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [balanceError, setBalanceError] = useState<string | null>(null);
  const [balanceChange, setBalanceChange] = useState<BalanceChange | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [views, setViews] = useState<Record<number, TicketView>>({});
  const [starting, setStarting] = useState<number | null>(null);
  const [resetting, setResetting] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const viewsRef = useRef(views);
  viewsRef.current = views;
  const connectionRef = useRef(connection);
  connectionRef.current = connection;
  const cursors = useRef<Record<number, string | null>>({});
  const balanceRef = useRef<Balance | null>(null);
  const announcedRuns = useRef<Set<string>>(new Set());

  const patchView = useCallback(
    (id: number, patch: Partial<TicketView> | ((v: TicketView) => Partial<TicketView>)) =>
      setViews((prev) => {
        const cur = prev[id] ?? EMPTY_VIEW;
        return { ...prev, [id]: { ...cur, ...(typeof patch === "function" ? patch(cur) : patch) } };
      }),
    [],
  );

  const toast = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((ts) => [...ts.slice(-3), { ...t, id }]);
    window.setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), 7000);
  }, []);
  const dismissToast = useCallback((id: number) => setToasts((ts) => ts.filter((x) => x.id !== id)), []);

  /** Every request goes through here so the connection indicator reflects reality. */
  const call = useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
    try {
      const result = await fn();
      setConnection("online");
      setConnectionError(null);
      return result;
    } catch (e) {
      if (e instanceof ApiError && e.isNetwork) {
        setConnection("offline");
        setConnectionError(e.message);
      } else if (e instanceof ApiError) {
        setConnection("online"); // the backend answered, even if with an error
      }
      throw e;
    }
  }, []);

  // --- loaders ---------------------------------------------------------------

  const loadTickets = useCallback(async () => {
    try {
      const r = await call(api.tickets);
      setTickets(r.tickets);
      setShopDate(r.shop_date);
      setTicketsError(null);
      setSelectedId((cur) => cur ?? r.tickets[0]?.ticket_id ?? null);
      return r.tickets;
    } catch (e) {
      setTicketsError(errorMessage(e));
      return null;
    }
  }, [call]);

  const loadBalance = useCallback(async () => {
    try {
      const b = await call(api.balance);
      const prev = balanceRef.current;
      if (prev && prev.balance !== b.balance) setBalanceChange({ from: prev.balance, to: b.balance, at: Date.now() });
      balanceRef.current = b;
      setBalance(b);
      setBalanceError(null);
    } catch (e) {
      setBalanceError(errorMessage(e));
    }
  }, [call]);

  const loadDetail = useCallback(
    async (id: number) => {
      try {
        const d = await call(() => api.ticket(id));
        patchView(id, { detail: d, detailError: undefined });
      } catch (e) {
        patchView(id, { detailError: errorMessage(e) });
      }
    },
    [call, patchView],
  );

  const loadEvents = useCallback(
    async (id: number) => {
      const fetchOnce = async () => {
        const after = cursors.current[id] ?? null;
        const r = await call(() => api.events({ ticket_id: id, after, limit: after ? 200 : 300 }));
        if (r.next_after) cursors.current[id] = r.next_after;
        patchView(id, (v) => ({ events: mergeEvents(v.events, r.events), eventsLoaded: true, eventsError: undefined }));
      };
      try {
        await fetchOnce();
      } catch (e) {
        if (e instanceof ApiError && e.code === "event_not_found") {
          cursors.current[id] = null; // cursor no longer valid: reload from scratch, once
          try {
            await fetchOnce();
            return;
          } catch (e2) {
            e = e2;
          }
        }
        patchView(id, { eventsLoaded: true, eventsError: errorMessage(e) });
      }
    },
    [call, patchView],
  );

  const loadProposals = useCallback(
    async (id: number) => {
      try {
        const r = await call(() => api.proposals(id));
        patchView(id, { proposals: r.proposals, proposalsLoaded: true, proposalsError: undefined });
      } catch (e) {
        patchView(id, { proposalsLoaded: true, proposalsError: errorMessage(e) });
      }
    },
    [call, patchView],
  );

  const loadRun = useCallback(
    async (id: number, runId: string): Promise<RunDetail | null> => {
      try {
        const r = await call(() => api.run(runId));
        patchView(id, { run: r, runUnavailable: undefined });
        return r;
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) patchView(id, { runUnavailable: runId });
        return null;
      }
    },
    [call, patchView],
  );

  const refreshAll = useCallback(async () => {
    await Promise.all([loadTickets(), loadBalance()]);
  }, [loadTickets, loadBalance]);

  // --- initial load and ticket selection ----------------------------------------------

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    if (selectedId == null || !tickets) return;
    const t = tickets.find((x) => x.ticket_id === selectedId);
    if (!t) return;
    const v = viewsRef.current[selectedId];
    if (!v?.detail) void loadDetail(selectedId);
    if (!v?.eventsLoaded) void loadEvents(selectedId);
    void loadProposals(selectedId);
    const runId = t.active_run?.run_id ?? t.latest_run?.run_id ?? v?.run?.run_id;
    if (runId && v?.run?.run_id !== runId && v?.runUnavailable !== runId) void loadRun(selectedId, runId);
  }, [selectedId, tickets, loadDetail, loadEvents, loadProposals, loadRun]);

  // --- active runs and polling ---------------------------------------------------------

  const activeRuns = useMemo(() => {
    const m = new Map<number, string>();
    const finished = (tid: number, rid: string) => {
      const v = views[tid];
      return v?.runUnavailable === rid || (v?.run?.run_id === rid && v.run.state !== "running");
    };
    tickets?.forEach((t) => {
      if (t.active_run?.state === "running" && !finished(t.ticket_id, t.active_run.run_id)) {
        m.set(t.ticket_id, t.active_run.run_id);
      }
    });
    Object.entries(views).forEach(([tid, v]) => {
      if (v.run?.state === "running" && v.runUnavailable !== v.run.run_id) m.set(Number(tid), v.run.run_id);
    });
    return m;
  }, [tickets, views]);

  const activeKey = [...activeRuns.entries()].map(([t, r]) => `${t}:${r}`).sort().join(",");

  useEffect(() => {
    if (!activeKey) return;
    const entries = activeKey.split(",").map((s) => {
      const [t, r] = s.split(":");
      return [Number(t), r] as const;
    });
    let stopped = false;
    let busy = false;
    const tick = async () => {
      if (busy || stopped) return;
      busy = true;
      try {
        await Promise.all(
          entries.map(async ([tid, rid]) => {
            await loadEvents(tid);
            const run = await loadRun(tid, rid);
            if (stopped || announcedRuns.current.has(rid)) return;
            if (run === null && viewsRef.current[tid]?.runUnavailable === rid) {
              announcedRuns.current.add(rid);
              await loadTickets();
              return;
            }
            if (run && run.state !== "running") {
              announcedRuns.current.add(rid);
              await Promise.all([loadTickets(), loadBalance(), loadProposals(tid), loadEvents(tid)]);
              toast(
                run.state === "failed"
                  ? { tone: "danger", title: `Ticket ${tid}: run failed`, message: run.error ?? undefined }
                  : {
                      tone: "neutral",
                      title: `Ticket ${tid}: agent run finished`,
                      message: run.workflow_status ? WORKFLOW_LABEL[run.workflow_status] : undefined,
                    },
              );
            }
          }),
        );
      } finally {
        busy = false;
      }
    };
    void tick();
    const handle = window.setInterval(tick, connection === "offline" ? 8000 : 2500);
    return () => {
      stopped = true;
      window.clearInterval(handle);
    };
  }, [activeKey, connection, loadEvents, loadRun, loadTickets, loadBalance, loadProposals, toast]);

  // Light heartbeat while idle, so a stopped backend shows as disconnected.
  useEffect(() => {
    if (activeKey) return;
    const handle = window.setInterval(
      async () => {
        const wasOffline = connectionRef.current !== "online";
        try {
          await call(api.health);
          if (wasOffline) void recoverRef.current();
        } catch {
          /* the connection state has already been updated */
        }
      },
      connection === "offline" ? 8000 : 20000,
    );
    return () => window.clearInterval(handle);
  }, [activeKey, connection, call]);

  // --- actions -----------------------------------------------------------------------------

  const startRun = useCallback(
    async (id: number) => {
      setStarting(id);
      patchView(id, { runFeedback: undefined });
      try {
        const r = await call(() => api.startRun(id));
        patchView(id, { runFeedback: { tone: "success", message: `Run ${r.run_id} started.` }, runUnavailable: undefined });
        await loadRun(id, r.run_id);
        await loadTickets();
      } catch (e) {
        patchView(id, { runFeedback: { tone: "danger", message: errorMessage(e) } });
        void loadTickets();
      } finally {
        setStarting(null);
      }
    },
    [call, patchView, loadRun, loadTickets],
  );

  /** Submits a human approval. Throws ApiError on refusal; always refreshes from the backend. */
  const approve = useCallback(
    async (proposal: Proposal, approvedBy: string): Promise<ApprovalResult> => {
      try {
        const result = await call(() =>
          api.approve(proposal.id, {
            approved_by: approvedBy,
            confirm_amount: proposal.amount,
            confirm_payee: proposal.payee,
          }),
        );
        toast({
          tone: "success",
          title: result.outcome === "executed" ? "Payment executed" : "Purchase order approved",
          message: result.message,
        });
        return result;
      } finally {
        await Promise.all([
          loadProposals(proposal.ticket_id),
          loadBalance(),
          loadTickets(),
          loadEvents(proposal.ticket_id),
        ]);
      }
    },
    [call, toast, loadProposals, loadBalance, loadTickets, loadEvents],
  );

  /** Records a human decline. Throws ApiError on refusal; always refreshes from the backend. */
  const decline = useCallback(
    async (proposal: Proposal, declinedBy: string, reason: string): Promise<DeclineResult> => {
      try {
        const result = await call(() => api.decline(proposal.id, { declined_by: declinedBy, reason }));
        toast({ tone: "neutral", title: `Proposal #${proposal.id} declined`, message: "Nothing was paid, ordered or sent." });
        return result;
      } finally {
        await Promise.all([loadProposals(proposal.ticket_id), loadTickets(), loadEvents(proposal.ticket_id)]);
      }
    },
    [call, toast, loadProposals, loadTickets, loadEvents],
  );

  const reset = useCallback(async (): Promise<ResetResult | null> => {
    setResetting(true);
    try {
      const r = await call(api.reset);
      setViews((prev) =>
        Object.fromEntries(
          Object.entries(prev).map(([k, v]) => [
            k,
            { ...v, run: undefined, runUnavailable: undefined, runFeedback: undefined, proposals: [], proposalsLoaded: false, detail: undefined },
          ]),
        ),
      );
      toast({
        tone: "success",
        title: "Working database reset",
        message: `Checking restored to ${money(r.checking_balance, balanceRef.current?.currency)}; all tickets open.`,
      });
      await refreshAll();
      return r;
    } catch (e) {
      toast({ tone: "danger", title: "Reset refused", message: errorMessage(e) });
      return null;
    } finally {
      setResetting(false);
    }
  }, [call, toast, refreshAll]);

  /** Reload everything the operator is looking at (after a reconnect or a manual retry). */
  const recover = useCallback(async () => {
    await refreshAll();
    if (selectedId != null) {
      void loadEvents(selectedId);
      void loadProposals(selectedId);
    }
  }, [refreshAll, selectedId, loadEvents, loadProposals]);
  const recoverRef = useRef(recover);
  recoverRef.current = recover;

  const retry = useCallback(async () => {
    setConnection("connecting");
    await recover();
  }, [recover]);

  // --- derived ------------------------------------------------------------------------------

  const ticketStates = useMemo(() => {
    const m = new Map<number, ReturnType<typeof ticketState>>();
    tickets?.forEach((t) => {
      const v = views[t.ticket_id];
      const sessionRun = v?.run && v.runUnavailable !== v.run.run_id ? v.run : null;
      m.set(t.ticket_id, ticketState(t, sessionRun));
    });
    return m;
  }, [tickets, views]);

  const opsStatus = useMemo((): { label: string; tone: Tone; live?: boolean } => {
    if (connection === "offline") return { label: "Backend offline", tone: "danger" };
    if (connection === "connecting" && !tickets) return { label: "Connecting…", tone: "neutral" };
    if (activeRuns.size) return { label: `Workflow running · ${activeRuns.size}`, tone: "progress", live: true };
    const attention = [...ticketStates.values()].filter((s) =>
      ["attention", "blocked", "failed"].includes(s.key),
    ).length;
    if (attention) return { label: `Attention required · ${attention}`, tone: "attention" };
    return { label: "Agents idle", tone: "neutral" };
  }, [connection, tickets, activeRuns, ticketStates]);

  return {
    connection,
    connectionError,
    tickets,
    ticketsError,
    shopDate,
    balance,
    balanceError,
    balanceChange,
    selectedId,
    setSelectedId,
    views,
    starting,
    resetting,
    activeRuns,
    ticketStates,
    opsStatus,
    toasts,
    dismissToast,
    startRun,
    approve,
    decline,
    reset,
    retry,
    reloadTicket: (id: number) => {
      void loadDetail(id);
      void loadEvents(id);
      void loadProposals(id);
    },
  };
}

export type Desk = ReturnType<typeof useDesk>;
