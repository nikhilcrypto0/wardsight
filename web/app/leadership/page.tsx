"use client";

import { useEffect, useState } from "react";
import { api, type Leadership } from "../lib/api";
import { CONDITION } from "../lib/labels";

function pct(value: number | null): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function signed(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(4)}`;
}

function LeadershipScreen() {
  const [data, setData] = useState<Leadership | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.leadership().then(setData).catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load"));
  }, []);

  if (error) return <p className="text-rose-700">{error}</p>;
  if (!data) return <p className="text-slate-500">Loading…</p>;

  const cmi = data.case_mix;
  const q = data.queries;
  const funnel: [string, number, string][] = [
    ["Gaps found, query drafted", q.drafted, "bg-slate-400"],
    ["Approved and sent", q.sent, "bg-violet-500"],
    ["Physician answered", q.answered, "bg-amber-500"],
    ["Resolved", q.resolved, "bg-emerald-600"],
  ];
  const top = Math.max(q.drafted, 1);

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">Leadership view</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">
          How complete the record is, and what the query program has done about it. Case mix index (CMI) is the
          average billing weight of the {cmi.cases} stays; it rises when complications are documented and falls
          when unsupported diagnoses are ruled out. Shown in weight points, not dollars.
        </p>
      </section>

      <section className="grid gap-px overflow-hidden rounded-xl bg-slate-200 ring-1 ring-slate-200 md:grid-cols-3">
        {[
          ["As first documented", cmi.first_documented, "text-slate-500"],
          ["Now", cmi.current, "text-slate-900"],
          ["If every open gap is resolved", cmi.if_all_resolved, "text-teal-700"],
        ].map(([label, value, tone]) => (
          <div key={label as string} className="bg-white px-6 py-5">
            <div className="text-xs uppercase tracking-wide text-slate-500">CMI · {label}</div>
            <div className={`mt-1 font-mono text-4xl tracking-tight ${tone}`}>{(value as number).toFixed(4)}</div>
            {label !== "As first documented" && (
              <div className="mt-1 font-mono text-xs text-slate-500">
                {signed((value as number) - cmi.first_documented)} vs first documented
              </div>
            )}
          </div>
        ))}
      </section>

      <div className="grid gap-8 lg:grid-cols-2">
        <section className="rounded-xl bg-white p-5 ring-1 ring-slate-200">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Query workflow</h2>
          <div className="mt-4 space-y-3">
            {funnel.map(([label, value, color]) => (
              <div key={label}>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-700">{label}</span>
                  <span className="font-mono">{value}</span>
                </div>
                <div className="mt-1 h-2 rounded-full bg-slate-100">
                  <div className={`h-2 rounded-full ${color}`} style={{ width: `${(value / top) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
          <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-slate-100 pt-4 text-sm">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Response rate</dt>
              <dd className="font-mono text-xl">{pct(q.response_rate)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Agreement rate</dt>
              <dd className="font-mono text-xl">{pct(q.agreement_rate)}</dd>
            </div>
          </dl>
          {q.sent === 0 && (
            <p className="mt-3 text-xs text-slate-500">No queries sent yet. Approve some from the worklist.</p>
          )}
        </section>

        <section className="rounded-xl bg-white p-5 ring-1 ring-slate-200">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">By condition</h2>
          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="py-2 font-medium">Condition</th>
                <th className="py-2 font-medium text-right">Missing</th>
                <th className="py-2 font-medium text-right">Unsupported</th>
                <th className="py-2 font-medium text-right">Resolved</th>
                <th className="py-2 font-medium text-right">Weight change</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.by_condition.map((r) => (
                <tr key={r.condition}>
                  <td className="py-2">{CONDITION[r.condition]}</td>
                  <td className="py-2 text-right font-mono">{r.missing}</td>
                  <td className="py-2 text-right font-mono">{r.unsupported}</td>
                  <td className="py-2 text-right font-mono">{r.resolved}</td>
                  <td className={`py-2 text-right font-mono ${r.weight_change > 0 ? "text-teal-700" : r.weight_change < 0 ? "text-rose-700" : "text-slate-400"}`}>
                    {r.weight_change === 0 ? "0" : signed(r.weight_change)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
      <p className="text-xs text-slate-400">Weights: {data.weights_source}.</p>
    </div>
  );
}

export default function LeadershipPage() {
  return <LeadershipScreen />;
}
