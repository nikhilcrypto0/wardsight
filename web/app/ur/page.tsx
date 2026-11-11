"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type UrBoard, type UrStatus } from "../lib/api";

const STATUS: Record<UrStatus, [string, string]> = {
  long_stay: ["Long stay: review barriers", "bg-rose-50 text-rose-700 ring-rose-200"],
  observation_review: ["Observation review", "bg-orange-50 text-orange-700 ring-orange-200"],
  explained_by_gap: ["Explained by a documentation gap", "bg-violet-50 text-violet-700 ring-violet-200"],
  no_benchmark: ["No benchmark", "bg-slate-100 text-slate-600 ring-slate-200"],
  ok: ["Within expected stay", "bg-emerald-50 text-emerald-700 ring-emerald-200"],
};

const FILTERS: ("needs_review" | "explained_by_gap" | "all")[] = ["needs_review", "explained_by_gap", "all"];
const FILTER_LABEL = { needs_review: "Needs review", explained_by_gap: "Explained by a gap", all: "All stays" };

/** Bar comparing the actual stay with the expected stay (GMLOS) on a shared day scale. */
function StayBar({ los, gmlos, max }: { los: number; gmlos: number | null; max: number }) {
  const pct = (d: number) => `${Math.min(100, (d / max) * 100)}%`;
  return (
    <div className="relative h-2.5 w-40 rounded-full bg-slate-100" aria-hidden>
      <div className="absolute inset-y-0 left-0 rounded-full bg-slate-400" style={{ width: pct(los) }} />
      {gmlos != null && <div className="absolute -inset-y-1 w-0.5 bg-teal-700" style={{ left: pct(gmlos) }} />}
    </div>
  );
}

function UrScreen() {
  const [board, setBoard] = useState<UrBoard | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("needs_review");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.ur().then(setBoard).catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load"));
  }, []);

  const rows = useMemo(() => {
    const all = board?.rows ?? [];
    if (filter === "all") return all;
    if (filter === "explained_by_gap") return all.filter((r) => r.status === "explained_by_gap");
    return all.filter((r) => r.status === "long_stay" || r.status === "observation_review");
  }, [board, filter]);

  if (error) return <p className="text-rose-700">{error}</p>;
  if (!board) return <p className="text-slate-500">Loading utilization review…</p>;

  const maxDays = Math.max(...board.rows.map((r) => Math.max(r.los_days, r.gmlos ?? 0)), 1);
  const c = board.counts;

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">Utilization review</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">
          Each stay against the CMS two-midnight benchmark and the expected length of stay (GMLOS) for its
          billing category. Some stays only look long because the record is incomplete: once the missing
          diagnosis is documented, the true category&apos;s expected stay covers them.
        </p>
      </section>

      <section className="grid grid-cols-2 md:grid-cols-4 divide-x divide-slate-200 rounded-xl bg-white ring-1 ring-slate-200">
        {[
          [c.long_stay ?? 0, "Long stays to review", "text-rose-700"],
          [c.observation_review ?? 0, "Observation reviews", "text-orange-700"],
          [c.explained_by_gap ?? 0, "Explained by a gap", "text-violet-700"],
          [c.ok ?? 0, "Within expected stay", "text-emerald-700"],
        ].map(([value, label, tone]) => (
          <div key={label as string} className="px-5 py-4">
            <div className={`font-mono text-3xl ${tone}`}>{value}</div>
            <div className="mt-1 text-xs uppercase tracking-wide text-slate-500">{label}</div>
          </div>
        ))}
      </section>

      <section className="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
        <div className="flex gap-1 border-b border-slate-200 p-3">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-md px-3 py-1.5 text-sm ${filter === f ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}
            >
              {FILTER_LABEL[f]}
            </button>
          ))}
          <span className="ml-auto self-center text-xs text-slate-500">
            <span className="mr-1 inline-block h-2.5 w-4 rounded-full bg-slate-400 align-middle" /> actual stay
            <span className="ml-3 mr-1 inline-block h-3 w-0.5 bg-teal-700 align-middle" /> expected (GMLOS)
          </span>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2.5 font-medium">Patient</th>
              <th className="px-4 py-2.5 font-medium">Billing category</th>
              <th className="px-4 py-2.5 font-medium">Stay vs expected</th>
              <th className="px-4 py-2.5 font-medium">Midnights</th>
              <th className="px-4 py-2.5 font-medium">Review</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => (
              <tr key={r.encounter_id} className="hover:bg-slate-50 align-top">
                <td className="px-4 py-3">
                  <Link href={`/encounters/${r.encounter_id}`} className="font-mono text-blue-700 hover:underline">
                    {r.encounter_id}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <span className="font-mono">{r.drg}</span>{" "}
                  <span className="text-slate-500">{r.drg_description}</span>
                </td>
                <td className="px-4 py-3">
                  <StayBar los={r.los_days} gmlos={r.gmlos} max={maxDays} />
                  <div className="mt-1 font-mono text-xs text-slate-500">
                    {r.los_days} d vs {r.gmlos ?? "?"} d
                  </div>
                </td>
                <td className="px-4 py-3 font-mono">{r.midnights}</td>
                <td className="px-4 py-3 max-w-sm">
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${STATUS[r.status][1]}`}>
                    {STATUS[r.status][0]}
                  </span>
                  {r.note && <p className="mt-1 text-xs text-slate-600">{r.note}</p>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="p-6 text-sm text-slate-500">Nothing in this view.</p>}
      </section>
      <p className="text-xs text-slate-400">
        Expected stays and weights: CMS IPPS FY2027 Table 5 (MS-DRG v44). Verify against the CMS file before real use.
      </p>
    </div>
  );
}

export default function UrPage() {
  return <UrScreen />;
}
