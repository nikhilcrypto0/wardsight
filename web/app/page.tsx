"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type Status, type Summary, type WorklistRow } from "./lib/api";
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

export default function WorklistPage() {
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

  const shown = useMemo(
    () => (rows ?? []).filter((r) => filter === "all" || r.status === filter),
    [rows, filter],
  );

  if (error) return <p className="text-rose-700">{error}. Is the API running (uv run wardsight-api)?</p>;
  if (!rows || !summary) return <p className="text-slate-500">Loading worklist…</p>;

  const q = summary.queries;
  const openFlags = (summary.open_flags.missing_dx ?? 0) + (summary.open_flags.unsupported_dx ?? 0);

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">Clinical documentation worklist</h1>
        <p className="mt-1 text-sm text-slate-500">
          {summary.charts} admitted patients scanned. Each row is a gap between what the chart shows and what the
          notes say, with a draft physician query waiting for review.
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
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-slate-500 bg-slate-50">
            <tr>
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
        {shown.length === 0 && <p className="p-6 text-sm text-slate-500">Nothing in this view.</p>}
      </section>
    </div>
  );
}
