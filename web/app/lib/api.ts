// Typed client for the WardSight Python API (proxied at /api by next.config.ts).
// The hosted demo has no API: there the same calls run in the browser (lib/demo.ts).

import { demoApi } from "./demo";
import { IS_PUBLIC } from "./mode";

export type Kind = "missing_dx" | "unsupported_dx" | "unspecified_dx" | "conflicting_dx";
export type Status = "pending_review" | "needs_rewrite" | "rejected" | "sent" | "answered" | "resolved";

export interface PriorityPart {
  label: string;
  points: number;
  why: string;
}

export interface WorklistRow {
  query_id: string;
  encounter_id: string;
  condition: string;
  kind: Kind;
  status: Status;
  reason_for_admission: string;
  age: number;
  sex: string;
  drg_now: number | null;
  severity_now: string | null;
  drg_if_resolved: number | null;
  severity_if_resolved: string | null;
  drg_before: number | null;
  drg_after: number | null;
  answer: string | null;
  los_days: number;
  /** 0-100, how urgently a reviewer should work this gap; null once the gap is closed */
  priority: number | null;
  priority_parts: PriorityPart[] | null;
}

export interface Summary {
  charts: number;
  open_flags: Partial<Record<Kind, number>>;
  queries: Partial<Record<Status, number>>;
}

export interface Flag {
  condition: string;
  kind: Kind;
  icd10: string;
  detail: string;
  evidence: string;
  drg_now: number;
  drg_now_desc: string;
  severity_now: string;
  drg_if_resolved: number;
  drg_if_resolved_desc: string;
  severity_if_resolved: string;
}

export interface Query {
  query_id: string;
  condition: string;
  kind: Kind;
  stem: string;
  options: string[];
  indicators: string[];
  status: Status;
  problems: string[];
  answer: string | null;
  answer_comment: string | null;
  answered_by: string | null;
  drg_before: number | null;
  drg_after: number | null;
}

export type Series = Record<string, [number, number][]>;

export interface DrgStep {
  hour: number;
  day: number;
  source: string;
  drg: number;
  description: string;
  severity: string;
  weight: number | null;
  added: { code: string; name: string }[];
  removed: { code: string; name: string }[];
  open_gaps: number;
  potential_drg: number;
  potential_description: string;
}

export interface Encounter {
  encounter_id: string;
  age: number;
  sex: string;
  los_days: number;
  reason_for_admission: string;
  problem_list: string[];
  drg: { drg: number; description: string; severity: string; principal: string; secondary: string[] };
  series: Series;
  labs: Series;
  timeline: { t: number; kind: string; text: string }[];
  notes: { type: string; day: number; text: string }[];
  flags: Flag[];
  drg_timeline: DrgStep[];
  queries: Query[];
}

export interface InboxItem extends Query {
  encounter_id: string;
  reason_for_admission: string;
  age: number;
  sex: string;
}

export interface AuditRow {
  ts: string;
  actor: string;
  action: string;
  query_id: string;
  detail: string;
}

export interface ClinicalRule {
  key: string;
  condition: string;
  source: string;
  rule: string;
}

export interface Packet {
  query_id: string;
  encounter_id: string;
  patient: { age: number; sex: string; reason_for_admission: string; los_days: number };
  condition: string;
  condition_name: string;
  alert: Kind;
  evidence: string[];
  rules: ClinicalRule[];
  query: {
    stem: string;
    options: string[];
    drafter: string;
    standard: string;
    rules_check: { ok: boolean; problems: string[] };
  };
  approval: { by: string; at?: string; edited: boolean } | null;
  answer: { option: string | null; comment: string | null; by: string | null; at?: string | null };
  addendum: string | null;
  outcome: {
    status: Status;
    drg_before: number | null;
    drg_after: number | null;
    weight_before: number | null;
    weight_after: number | null;
  };
  trail: { ts?: string; actor: string; action: string; detail: string }[];
}

export type UrStatus = "ok" | "observation_review" | "long_stay" | "explained_by_gap" | "no_benchmark";

export interface UrRow {
  encounter_id: string;
  drg: number;
  drg_description: string;
  gmlos: number | null;
  los_days: number;
  midnights: number;
  status: UrStatus;
  note: string;
  drg_if_documented: number | null;
  gmlos_if_documented: number | null;
}

export interface UrBoard {
  counts: Partial<Record<UrStatus, number>>;
  rows: UrRow[];
}

export interface Leadership {
  case_mix: { first_documented: number; current: number; if_all_resolved: number; cases: number };
  queries: {
    drafted: number;
    sent: number;
    answered: number;
    resolved: number;
    pending_review: number;
    response_rate: number | null;
    agreement_rate: number | null;
  };
  by_condition: {
    condition: string;
    gaps: number;
    missing: number;
    unsupported: number;
    unspecified: number;
    conflicting: number;
    resolved: number;
    weight_change: number;
  }[];
  weights_source: string;
  responses: {
    median_hours_to_answer: number | null;
    stale_after_hours: number;
    stale: { query_id: string; encounter_id: string; hours_waiting: number }[];
    by_physician: { physician: string; answered: number; agreed: number; agreement_rate: number }[];
  };
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown = {}) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body) });

const liveApi = {
  summary: () => call<Summary>("/api/summary"),
  worklist: () => call<WorklistRow[]>("/api/worklist"),
  encounter: (id: string) => call<Encounter>(`/api/encounters/${encodeURIComponent(id)}`),
  lint: (queryId: string, stem: string) =>
    post<{ ok: boolean; problems: string[] }>("/api/lint", { query_id: queryId, stem }),
  approve: (queryId: string, stem?: string) => post(`/api/queries/${queryId}/approve`, { stem }),
  reject: (queryId: string, reason: string) => post(`/api/queries/${queryId}/reject`, { reason }),
  inbox: () => call<InboxItem[]>("/api/inbox"),
  answer: (queryId: string, optionIndex: number, comment: string) =>
    post<{ status: Status }>(`/api/queries/${queryId}/answer`, { option_index: optionIndex, comment }),
  simulate: (queryId: string) => post<{ status: Status }>(`/api/queries/${queryId}/simulate`),
  audit: () => call<AuditRow[]>("/api/audit"),
  packet: (queryId: string) => call<Packet>(`/api/queries/${encodeURIComponent(queryId)}/packet`),
  ur: () => call<UrBoard>("/api/ur"),
  leadership: () => call<Leadership>("/api/leadership"),
  reset: () => post("/api/admin/reset"),
};

export type Api = typeof liveApi;

export const api: Api = IS_PUBLIC ? demoApi : liveApi;
