// Hosted-demo backend: the same interface as the live API, run in the visitor's browser.
//
// web/public/demo/ is exported by `uv run wardsight-demo`: the dev ward as it stands before
// review, plus, for every query and every answer, what the Python engine did after approving,
// answering and rescanning. This file only replays those recorded outcomes and keeps each
// visitor's progress in their own browser, so visitors never share or change real data.

import type {
  Api,
  AuditRow,
  Encounter,
  Flag,
  InboxItem,
  Kind,
  Leadership,
  Query,
  Status,
  Summary,
  UrBoard,
  UrRow,
  WorklistRow,
} from "./api";
import { lintQuery } from "./lint.ts";

interface Outcome {
  status: "answered" | "resolved";
  drg_before: number;
  drg_after: number;
  addendum: string | null;
  drg: Encounter["drg"];
  flags: Flag[];
  ur_row: UrRow;
  drgs: [number, number, number];
}

interface DemoQuery {
  query_id: string;
  encounter_id: string;
  condition: string;
  kind: Kind;
  stem: string;
  status: Status;
  reason_for_admission: string;
  age: number;
  sex: string;
  options: string[];
  indicators: string[];
  problems: string[];
  flag_kinds: Kind[];
  simulated: { option_index: number; comment: string };
  outcomes: Outcome[];
}

interface DemoIndex {
  charts: number;
  physician: string;
  reviewer: string;
  worklist: WorklistRow[];
  queries: Record<string, DemoQuery>;
  ur: UrBoard;
  case_mix_drgs: Record<string, [number, number, number]>;
  weights: Record<string, number>;
  weights_source: string;
  lint_targets: Record<string, string[]>;
}

interface QueryState {
  status: Status;
  stem?: string;
  option?: number;
  comment?: string;
  answered_by?: string;
  updated: string;
}

interface DemoState {
  queries: Record<string, QueryState>;
  audit: AuditRow[];
}

const STORAGE_KEY = "wardsight-demo-v1";
const UR_ORDER: Record<string, number> = {
  long_stay: 0,
  observation_review: 1,
  explained_by_gap: 2,
  no_benchmark: 3,
  ok: 4,
};

let indexPromise: Promise<DemoIndex> | null = null;
let memoryState: DemoState = { queries: {}, audit: [] };

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(res.status === 404 ? "not found" : `Could not load demo data (${res.status})`);
  return res.json() as Promise<T>;
}

function index(): Promise<DemoIndex> {
  indexPromise ??= fetchJson<DemoIndex>("/demo/index.json").catch((e: unknown) => {
    indexPromise = null;
    throw e;
  });
  return indexPromise;
}

// Browser storage can be missing or blocked (private windows); fall back to memory.
function loadState(): DemoState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) memoryState = JSON.parse(raw) as DemoState;
  } catch {
    /* keep the in-memory state */
  }
  return memoryState;
}

function saveState(state: DemoState): void {
  memoryState = state;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* in-memory only */
  }
}

const now = () => new Date().toISOString();
const round = (x: number, places: number) => Math.round(x * 10 ** places) / 10 ** places;

function withAudit(state: DemoState, actor: string, action: string, queryId: string, detail: string): DemoState {
  return { ...state, audit: [...state.audit, { ts: now(), actor, action, query_id: queryId, detail }] };
}

function current(q: DemoQuery, state: DemoState): QueryState {
  return state.queries[q.query_id] ?? { status: q.status, updated: "" };
}

function outcomeOf(q: DemoQuery, s: QueryState): Outcome | null {
  return (s.status === "answered" || s.status === "resolved") && s.option != null ? q.outcomes[s.option] : null;
}

function queryView(q: DemoQuery, s: QueryState): Query {
  const o = outcomeOf(q, s);
  return {
    query_id: q.query_id,
    condition: q.condition,
    kind: q.kind,
    stem: s.stem ?? q.stem,
    options: q.options,
    indicators: q.indicators,
    status: s.status,
    problems: q.problems,
    answer: o && s.option != null ? q.options[s.option] : null,
    answer_comment: o ? (s.comment ?? "") : null,
    answered_by: o ? (s.answered_by ?? null) : null,
    drg_before: o ? o.drg_before : null,
    drg_after: o ? o.drg_after : null,
  };
}

function requireStatus(q: DemoQuery, s: QueryState, ...allowed: Status[]): void {
  if (!allowed.includes(s.status)) {
    throw new Error(`query ${q.query_id} is '${s.status}'; this action needs ${allowed.join(" or ")}`);
  }
}

async function getQuery(queryId: string): Promise<[DemoQuery, DemoState]> {
  const q = (await index()).queries[queryId];
  if (!q) throw new Error(`not found: '${queryId}'`);
  return [q, loadState()];
}

function cmi(drgs: number[], weights: Record<string, number>): number {
  const w = drgs.map((d) => weights[String(d)]).filter((x): x is number => x != null);
  return w.length ? round(w.reduce((a, b) => a + b, 0) / w.length, 4) : 0;
}

async function answerWith(queryId: string, option: number, comment: string, physician: string) {
  const [q, state] = await getQuery(queryId);
  const s = current(q, state);
  requireStatus(q, s, "sent");
  const o = q.outcomes[option];
  if (!o) throw new Error(`option ${option} does not exist`);
  let next: DemoState = {
    ...state,
    queries: {
      ...state.queries,
      [queryId]: { ...s, status: o.status, option, comment, answered_by: physician, updated: now() },
    },
  };
  next = withAudit(next, physician, "answered", queryId, `${q.options[option]} | ${comment}`);
  if (o.status === "resolved") {
    next = withAudit(next, "wardsight", "flag_resolved", queryId, `DRG ${o.drg_before} -> ${o.drg_after}`);
  }
  saveState(next);
  return { status: o.status as Status };
}

export const demoApi: Api = {
  async summary(): Promise<Summary> {
    const ix = await index();
    const state = loadState();
    const open: Partial<Record<Kind, number>> = {};
    const statuses: Partial<Record<Status, number>> = {};
    for (const q of Object.values(ix.queries)) {
      const s = current(q, state);
      statuses[s.status] = (statuses[s.status] ?? 0) + 1;
      const o = outcomeOf(q, s);
      for (const kind of o ? o.flags.map((f) => f.kind) : q.flag_kinds) open[kind] = (open[kind] ?? 0) + 1;
    }
    return { charts: ix.charts, open_flags: open, queries: statuses };
  },

  async worklist(): Promise<WorklistRow[]> {
    const ix = await index();
    const state = loadState();
    return ix.worklist.map((row) => {
      const q = ix.queries[row.query_id];
      const s = current(q, state);
      const o = outcomeOf(q, s);
      const resolved = o?.status === "resolved";
      return {
        ...row,
        status: s.status,
        drg_now: resolved ? null : row.drg_now,
        severity_now: resolved ? null : row.severity_now,
        drg_if_resolved: resolved ? null : row.drg_if_resolved,
        severity_if_resolved: resolved ? null : row.severity_if_resolved,
        drg_before: o ? o.drg_before : null,
        drg_after: o ? o.drg_after : null,
        answer: o && s.option != null ? q.options[s.option] : null,
      };
    });
  },

  async encounter(id: string): Promise<Encounter> {
    if (!/^[A-Z0-9-]+$/.test(id)) throw new Error("encounter not found");
    const [base, ix] = await Promise.all([fetchJson<Encounter>(`/demo/encounters/${id}.json`), index()]);
    const state = loadState();
    let chart: Encounter = { ...base, queries: [] };
    for (const q of Object.values(ix.queries).filter((x) => x.encounter_id === id)) {
      const s = current(q, state);
      const o = outcomeOf(q, s);
      if (o) {
        const notes = o.addendum
          ? [...chart.notes, { type: "addendum", day: base.los_days - 1, text: o.addendum + (s.comment ?? "") }]
          : chart.notes;
        chart = { ...chart, drg: o.drg, flags: o.flags, notes };
      }
      chart = { ...chart, queries: [...chart.queries, queryView(q, s)] };
    }
    return chart;
  },

  async lint(queryId: string, stem: string) {
    const [q] = await getQuery(queryId);
    const ix = await index();
    return lintQuery({ ...q, stem, targets: ix.lint_targets });
  },

  async approve(queryId: string, stem?: string) {
    const [q, state] = await getQuery(queryId);
    const ix = await index();
    const s = current(q, state);
    requireStatus(q, s, "pending_review", "needs_rewrite");
    const text = (stem ?? s.stem ?? q.stem).trim();
    const result = lintQuery({ ...q, stem: text, targets: ix.lint_targets });
    if (!result.ok) throw new Error(result.problems.join("; "));
    const next = withAudit(
      { ...state, queries: { ...state.queries, [queryId]: { ...s, status: "sent", stem: text, updated: now() } } },
      ix.reviewer,
      stem == null ? "approved_and_sent" : "edited_approved_and_sent",
      queryId,
      text,
    );
    saveState(next);
    return { status: "sent" };
  },

  async reject(queryId: string, reason: string) {
    const [q, state] = await getQuery(queryId);
    const ix = await index();
    const s = current(q, state);
    requireStatus(q, s, "pending_review", "needs_rewrite");
    saveState(
      withAudit(
        { ...state, queries: { ...state.queries, [queryId]: { ...s, status: "rejected", updated: now() } } },
        ix.reviewer,
        "rejected",
        queryId,
        reason,
      ),
    );
    return { status: "rejected" };
  },

  async inbox(): Promise<InboxItem[]> {
    const ix = await index();
    const state = loadState();
    return Object.values(ix.queries)
      .map((q) => ({ q, s: current(q, state) }))
      .filter(({ s }) => s.status === "sent" || s.status === "answered" || s.status === "resolved")
      .sort((a, b) => Number(b.s.status === "sent") - Number(a.s.status === "sent") || b.s.updated.localeCompare(a.s.updated))
      .map(({ q, s }) => ({
        ...queryView(q, s),
        encounter_id: q.encounter_id,
        reason_for_admission: q.reason_for_admission,
        age: q.age,
        sex: q.sex,
      }));
  },

  answer: (queryId: string, optionIndex: number, comment: string) =>
    answerWith(queryId, optionIndex, comment, "Attending physician"),

  async simulate(queryId: string) {
    const [q] = await getQuery(queryId);
    const ix = await index();
    return answerWith(queryId, q.simulated.option_index, q.simulated.comment, ix.physician);
  },

  async audit(): Promise<AuditRow[]> {
    return [...loadState().audit].reverse().slice(0, 300);
  },

  async ur(): Promise<UrBoard> {
    const ix = await index();
    const state = loadState();
    const replaced = new Map<string, UrRow>();
    for (const q of Object.values(ix.queries)) {
      const o = outcomeOf(q, current(q, state));
      if (o) replaced.set(q.encounter_id, o.ur_row);
    }
    const rows = ix.ur.rows
      .map((r) => replaced.get(r.encounter_id) ?? r)
      .sort((a, b) => UR_ORDER[a.status] - UR_ORDER[b.status] || (b.los_days - (b.gmlos ?? 0)) - (a.los_days - (a.gmlos ?? 0)));
    const counts: UrBoard["counts"] = {};
    for (const r of rows) counts[r.status] = (counts[r.status] ?? 0) + 1;
    return { counts, rows };
  },

  async leadership(): Promise<Leadership> {
    const ix = await index();
    const state = loadState();
    const drgs = { ...ix.case_mix_drgs };
    const statuses: Partial<Record<Status, number>> = {};
    const byCondition = new Map<string, Leadership["by_condition"][number]>();
    for (const q of Object.values(ix.queries)) {
      const s = current(q, state);
      const o = outcomeOf(q, s);
      if (o) drgs[q.encounter_id] = o.drgs;
      statuses[s.status] = (statuses[s.status] ?? 0) + 1;
      const row = byCondition.get(q.condition) ?? {
        condition: q.condition, gaps: 0, missing: 0, unsupported: 0, resolved: 0, weight_change: 0,
      };
      row.gaps += 1;
      if (q.kind === "missing_dx") row.missing += 1;
      else row.unsupported += 1;
      if (s.status === "resolved" && o) {
        row.resolved += 1;
        const [b, a] = [ix.weights[String(o.drg_before)], ix.weights[String(o.drg_after)]];
        if (b != null && a != null) row.weight_change = round(row.weight_change + a - b, 4);
      }
      byCondition.set(q.condition, row);
    }
    const all = Object.values(drgs);
    const answered = (statuses.answered ?? 0) + (statuses.resolved ?? 0);
    const sent = answered + (statuses.sent ?? 0);
    return {
      case_mix: {
        first_documented: cmi(all.map((d) => d[0]), ix.weights),
        current: cmi(all.map((d) => d[1]), ix.weights),
        if_all_resolved: cmi(all.map((d) => d[2]), ix.weights),
        cases: all.length,
      },
      queries: {
        drafted: Object.keys(ix.queries).length,
        sent,
        answered,
        resolved: statuses.resolved ?? 0,
        pending_review: statuses.pending_review ?? 0,
        response_rate: sent ? round(answered / sent, 3) : null,
        agreement_rate: answered ? round((statuses.resolved ?? 0) / answered, 3) : null,
      },
      by_condition: [...byCondition.values()].sort((a, b) => a.condition.localeCompare(b.condition)),
      weights_source: ix.weights_source,
    };
  },

  async reset() {
    saveState(withAudit({ queries: {}, audit: [] }, "demo", "reset", "", "your demo progress was cleared"));
    return { status: "reset" };
  },
};
