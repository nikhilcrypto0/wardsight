"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type Status, type Summary, type WorklistRow } from "./lib/api";
import { IS_PUBLIC } from "./lib/mode";
import { CONDITION, DrgShift, KindBadge, StatusBadge } from "./lib/labels";

const FILTERS: { key: "all" | Status; label: string }[] = [
  { key: "all", label: "All" },
  { key: "pending_review", label: "Needs review" },
  { key: "sent", label: "With physician" },
  { key: "answered", label: "Answered, open" },
  { key: "resolved", label: "Resolved" },
];

function Stat({ value, label, tone = "text-slate-900" }: { value: number; label: string; tone?: string }) {
  return (
    <div className="px-5 py-4 border-r border-slate-200 last:border-r-0">
      <div className={`font-mono text-3xl tracking-tight ${tone}`}>{value}</div>
      <div className="mt-1 text-xs uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}

export default function HomePage() {
  return <WorklistPage />;
}

function WorklistPage() {
  const [rows, setRows] = useState<WorklistRow[] | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [filter, setFilter] = useState<"all" | Status>("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.worklist(), api.summary()])
      .then(([w, s]) => {
        setRows(w);
        setSummary(s);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load the worklist"));
  }, []);

  // Highest priority first; closed gaps (no priority) sink to the bottom.
  const shown = useMemo(
    () =>
      (rows ?? [])
        .filter((r) => filter === "all" || r.status === filter)
        .toSorted((a, b) => (b.priority ?? -1) - (a.priority ?? -1) || a.encounter_id.localeCompare(b.encounter_id)),
    [rows, filter],
  );

  if (error)
    return (
      <p className="text-rose-700">
        {error}.{IS_PUBLIC ? " Try reloading the page." : " Is the API running (uv run wardsight-api)?"}
      </p>
    );
  if (!rows || !summary) return <p className="text-slate-500">Loading worklist…</p>;

  const q = summary.queries;
  // every alert type counts (missing, unsupported, not fully specified, conflicting)
  const openFlags = Object.values(summary.open_flags).reduce((sum, n) => sum + (n ?? 0), 0);

  return (
    <div className="space-y-8">
      {IS_PUBLIC && <DemoIntro charts={summary.charts} gaps={openFlags} />}
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">Clinical documentation worklist</h1>
        <p className="mt-1 text-sm text-slate-500">
          {summary.charts} admitted patients scanned. Each row is a gap between what the chart shows and what the
          notes say, with a draft physician query waiting for review. Sorted by priority: billing impact,
          complication level and time left before the expected discharge.
        </p>
      </section>

      <section className="grid grid-cols-2 md:grid-cols-5 bg-white rounded-xl ring-1 ring-slate-200">
        <Stat value={openFlags} label="Open gaps" />
        <Stat value={q.pending_review ?? 0} label="Queries to review" tone="text-blue-700" />
        <Stat value={q.sent ?? 0} label="With physician" tone="text-violet-700" />
        <Stat value={q.answered ?? 0} label="Answered, still open" tone="text-amber-700" />
        <Stat value={q.resolved ?? 0} label="Resolved" tone="text-emerald-700" />
      </section>

      <section className="bg-white rounded-xl ring-1 ring-slate-200 overflow-hidden">
        <div className="flex flex-wrap gap-1 p-3 border-b border-slate-200">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                filter === f.key ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-slate-500 bg-slate-50">
            <tr>
              <th className="px-4 py-2.5 font-medium">Priority (impact)</th>
              <th className="px-4 py-2.5 font-medium">Patient</th>
              <th className="px-4 py-2.5 font-medium">Admitted for</th>
              <th className="px-4 py-2.5 font-medium">Condition</th>
              <th className="px-4 py-2.5 font-medium">Gap</th>
              <th className="px-4 py-2.5 font-medium">DRG now → if resolved</th>
              <th className="px-4 py-2.5 font-medium">Query status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.map((r) => (
              <tr key={r.query_id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <PriorityCell row={r} />
                </td>
                <td className="px-4 py-3">
                  <Link href={`/encounters/${r.encounter_id}`} className="font-mono text-blue-700 hover:underline">
                    {r.encounter_id}
                  </Link>
                  <div className="text-xs text-slate-500">
                    {r.age} y, {r.sex}
                  </div>
                </td>
                <td className="px-4 py-3 text-slate-700">{r.reason_for_admission}</td>
                <td className="px-4 py-3 font-medium">{CONDITION[r.condition]}</td>
                <td className="px-4 py-3">
                  <KindBadge kind={r.kind} />
                </td>
                <td className="px-4 py-3">
                  {r.drg_before != null ? (
                    <DrgShift from={r.drg_before} to={r.drg_after} />
                  ) : (
                    <DrgShift from={r.drg_now} to={r.drg_if_resolved} />
                  )}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={r.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        {shown.length === 0 && <p className="p-6 text-sm text-slate-500">Nothing in this view.</p>}
      </section>
    </div>
  );
}

/** First thing a visitor to the hosted demo sees: what this is and where to click. */
function DemoIntro({ charts, gaps }: { charts: number; gaps: number }) {
  return (
    <section className="rounded-xl bg-slate-900 p-6 text-white">
      <p className="text-xs font-semibold uppercase tracking-wider text-teal-300">Try it: you are the CDI reviewer</p>
      <h2 className="mt-2 text-xl font-semibold tracking-tight">
        {charts} synthetic inpatients. The engine found {gaps} places where the chart and the notes disagree.
      </h2>
      <ol className="mt-4 grid gap-3 text-sm text-slate-300 md:grid-cols-3">
        <li>
          <span className="font-semibold text-white">1. Open a patient.</span> See the evidence the rule used, with
          the hour each value appeared, next to the notes that never name the diagnosis.
        </li>
        <li>
          <span className="font-semibold text-white">2. Review the draft query.</span> Edit it and the compliance check
          (ACDIS/AHIMA 2022) re-runs on every keystroke. Nothing is sent until you approve.
        </li>
        <li>
          <span className="font-semibold text-white">3. Let the physician answer.</span> The answer becomes an
          addendum, the chart is rescanned and the billing category updates. Every step is in the audit log.
        </li>
      </ol>
      <div className="mt-5 flex flex-wrap gap-3 text-sm">
        <Link href="/encounters/D0011" className="rounded-lg bg-teal-500 px-4 py-2 font-medium text-slate-900">
          Start with patient D0011 (sepsis missed on a UTI admission)
        </Link>
        <Link href="/replay" className="rounded-lg px-4 py-2 ring-1 ring-slate-600 hover:bg-slate-800">
          Watch 14 days of the ward in 15 seconds
        </Link>
      </div>
      <p className="mt-4 text-xs text-slate-400">
        Runs entirely in your browser from precomputed engine results: your clicks change only your copy. Reset it any
        time from the audit log.
      </p>
    </section>
  );
}

const SHORT: Record<string, string> = {
  "Billing impact": "Billing",
  "Complication level": "CC/MCC",
  "Time pressure": "Time",
};

/** The score and the parts it is made of, so a reviewer can see why a case is on top. */
function PriorityCell({ row }: { row: WorklistRow }) {
  if (row.priority == null || !row.priority_parts) return <span className="text-slate-400">closed</span>;
  // Both directions rank the same way: an unsupported diagnosis is a compliance risk, not a missed sale.
  const direction: Record<WorklistRow["kind"], [string, string]> = {
    missing_dx: ["Corrects up: missing diagnosis", "text-teal-700"],
    unspecified_dx: ["Corrects up: not fully specified", "text-teal-700"],
    unsupported_dx: ["Corrects down: unsupported diagnosis", "text-rose-700"],
    conflicting_dx: ["Clarifies: notes disagree", "text-violet-700"],
  };
  const [label, labelTone] = direction[row.kind];
  const tone = row.priority >= 60 ? "bg-rose-600" : row.priority >= 35 ? "bg-amber-500" : "bg-slate-400";
  return (
    <div title={row.priority_parts.map((p) => `${p.label}: +${p.points} (${p.why})`).join("\n")}>
      <div className="flex items-center gap-2">
        <span className={`inline-block h-2 w-2 rounded-full ${tone}`} />
        <span className="font-mono text-base font-medium">{row.priority}</span>
      </div>
      <div className={`mt-0.5 text-[11px] font-medium whitespace-nowrap ${labelTone}`}>{label}</div>
      <div className="text-[11px] text-slate-500 whitespace-nowrap">
        {row.priority_parts
          .filter((p) => p.points > 0)
          .map((p) => `${SHORT[p.label] ?? p.label} +${p.points}`)
          .join(" · ")}
      </div>
    </div>
  );
}
