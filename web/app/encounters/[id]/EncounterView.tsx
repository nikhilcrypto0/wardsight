"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import QueryCard from "../../components/QueryCard";
import Sparkline from "../../components/Sparkline";
import { api, type Encounter } from "../../lib/api";
import { CONDITION, DrgShift, KindBadge, SERIES_LABEL } from "../../lib/labels";

const TIMELINE_PREVIEW = 12;

export default function EncounterView() {
  const { id } = useParams<{ id: string }>();
  const [chart, setChart] = useState<Encounter | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [allEvents, setAllEvents] = useState(false);

  const load = useCallback(() => {
    api
      .encounter(id)
      .then(setChart)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load chart"));
  }, [id]);

  useEffect(load, [load]);

  if (error) return <p className="text-rose-700">{error}</p>;
  if (!chart) return <p className="text-slate-500">Loading chart…</p>;

  const events = allEvents ? chart.timeline : chart.timeline.slice(0, TIMELINE_PREVIEW);

  return (
    <div className="space-y-8">
      <Link href="/" className="text-sm text-slate-500 hover:text-slate-800">
        ← Worklist
      </Link>

      <section className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="font-mono text-2xl tracking-tight">{chart.encounter_id}</h1>
          <p className="mt-1 text-slate-600">
            {chart.age}-year-old {chart.sex}, admitted for {chart.reason_for_admission}, {chart.los_days}-day stay
          </p>
          {chart.problem_list.length > 0 && (
            <p className="mt-1 text-xs text-slate-500">Problem list: {chart.problem_list.join(", ")}</p>
          )}
        </div>
        <div className="rounded-xl bg-slate-900 text-white px-5 py-3">
          <div className="text-xs uppercase tracking-wide text-slate-400">Billing category as documented</div>
          <div className="mt-0.5 flex items-baseline gap-3">
            <span className="font-mono text-3xl">{chart.drg.drg}</span>
            <span className="text-sm text-slate-300 max-w-xs">{chart.drg.description}</span>
          </div>
        </div>
      </section>

      <div className="grid gap-8 lg:grid-cols-[1.1fr_1fr]">
        <section className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Gaps found</h2>
          {chart.flags.length === 0 && (
            <p className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800">
              No open gaps: the notes match what the chart shows.
            </p>
          )}
          {chart.flags.map((f) => (
            <article key={`${f.condition}-${f.kind}`} className="rounded-xl bg-white ring-1 ring-slate-200 p-5">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-semibold">{CONDITION[f.condition]}</h3>
                <KindBadge kind={f.kind} />
                <span className="ml-auto text-xs text-slate-500">
                  DRG <DrgShift from={f.drg_now} to={f.drg_if_resolved} />
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-600">{f.detail}</p>
              <ul className="mt-3 grid gap-1">
                {f.evidence.split(";").map((item) => (
                  <li key={item} className="font-mono text-xs text-slate-700 bg-slate-50 rounded px-2 py-1">
                    {item.trim()}
                  </li>
                ))}
              </ul>
            </article>
          ))}

          {chart.queries.map((q) => (
            <QueryCard key={q.query_id} query={q} onChanged={load} />
          ))}
        </section>

        <section className="space-y-6">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Trends over the stay</h2>
            <div className="mt-3 grid grid-cols-2 gap-3">
              {Object.entries(chart.series).map(([name, points]) => (
                <Sparkline key={name} name={name} points={points} />
              ))}
            </div>
          </div>

          {Object.keys(chart.labs).length > 0 && (
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Other results</h2>
              <table className="mt-2 w-full text-sm">
                <tbody className="divide-y divide-slate-100">
                  {Object.entries(chart.labs).flatMap(([name, points]) =>
                    points.map(([t, v]) => (
                      <tr key={`${name}-${t}`}>
                        <td className="py-1.5 text-slate-600">{SERIES_LABEL[name]?.[0] ?? name}</td>
                        <td className="py-1.5 font-mono">
                          {v} <span className="text-xs text-slate-400">{SERIES_LABEL[name]?.[1]}</span>
                        </td>
                        <td className="py-1.5 text-right font-mono text-xs text-slate-400">hour {t}</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
          )}

          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Orders, medications, imaging</h2>
            <ol className="mt-2 space-y-1 text-sm">
              {events.map((e, i) => (
                <li key={`${e.t}-${i}`} className="flex gap-3">
                  <span className="w-14 shrink-0 font-mono text-xs text-slate-400 pt-0.5">h{e.t}</span>
                  <span className="text-slate-700">{e.text}</span>
                </li>
              ))}
            </ol>
            {chart.timeline.length > TIMELINE_PREVIEW && (
              <button onClick={() => setAllEvents(!allEvents)} className="mt-2 text-sm text-teal-700 hover:underline">
                {allEvents ? "Show fewer" : `Show all ${chart.timeline.length}`}
              </button>
            )}
          </div>

          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Physician notes</h2>
            <div className="mt-2 space-y-2">
              {chart.notes.map((n, i) => (
                <details key={i} className="rounded-lg bg-white ring-1 ring-slate-200 p-3" open={n.type === "addendum"}>
                  <summary className="cursor-pointer text-sm font-medium">
                    {n.type.replaceAll("_", " ")} · day {n.day}
                    {n.type === "addendum" && <span className="ml-2 text-xs text-teal-700">new</span>}
                  </summary>
                  <p className="mt-2 whitespace-pre-line text-sm text-slate-700">{n.text}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
