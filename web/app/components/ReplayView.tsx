"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { CONDITION } from "../lib/labels";

interface Stay {
  id: string;
  bed: number;
  admit: number;
  discharge: number;
  age: number;
  sex: string;
  reason: string;
}

interface ReplayEvent {
  t: number;
  type: "admit" | "discharge" | "flag" | "query_sent" | "answered";
  encounter_id: string;
  condition?: string;
  kind?: "missing_dx" | "unsupported_dx";
  evidence?: string;
  answer?: string;
  resolved?: boolean;
  drg_from?: number;
  drg_to?: number;
}

interface Replay {
  beds: number;
  admit_days: number;
  hours: number;
  encounters: Stay[];
  events: ReplayEvent[];
}

type BedState = "empty" | "stable" | "gap" | "with_physician" | "open" | "resolved";

const REPLAY_SECONDS = 180; // the whole replay at 1x
const FEED_LENGTH = 9;
const SPEEDS = [1, 3, 10];

const BED_STYLE: Record<BedState, string> = {
  empty: "bg-slate-100 text-slate-300 ring-slate-200",
  stable: "bg-white text-slate-600 ring-slate-200",
  gap: "bg-amber-100 text-amber-900 ring-amber-400",
  with_physician: "bg-violet-100 text-violet-900 ring-violet-400",
  open: "bg-orange-50 text-orange-800 ring-orange-300",
  resolved: "bg-emerald-100 text-emerald-900 ring-emerald-400",
};

const LEGEND: [BedState, string][] = [
  ["stable", "Patient, no gap"],
  ["gap", "Gap found"],
  ["with_physician", "Query with physician"],
  ["resolved", "Resolved"],
  ["open", "Answered, still open"],
];

function clock(hour: number): string {
  const day = Math.floor(hour / 24) + 1;
  const h = Math.floor(hour % 24);
  return `Day ${day} · ${String(h).padStart(2, "0")}:00`;
}

function describe(e: ReplayEvent, stays: Map<string, Stay>): string {
  const name = e.condition ? CONDITION[e.condition] : "";
  switch (e.type) {
    case "admit":
      return `admitted, ${stays.get(e.encounter_id)?.reason ?? ""}`;
    case "flag":
      return e.kind === "missing_dx"
        ? `${name}: evidence found (${e.evidence}), not in the notes`
        : `${name}: documented, but the chart does not support it`;
    case "query_sent":
      return `${name}: query approved and sent to the physician`;
    case "answered":
      if (!e.resolved) return `${name}: physician answered “${e.answer}”. Still open`;
      return e.drg_from === e.drg_to
        ? `${name}: physician answered “${e.answer}”. Resolved; record now accurate, billing category unchanged`
        : `${name}: physician answered “${e.answer}”. Resolved, billing category ${e.drg_from} → ${e.drg_to}`;
    default:
      return "discharged";
  }
}

export default function ReplayView({ linkCharts = true }: { linkCharts?: boolean }) {
  const [data, setData] = useState<Replay | null>(null);
  const [hour, setHour] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const last = useRef<number | null>(null);

  useEffect(() => {
    fetch("/replay.json")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null));
  }, []);

  useEffect(() => {
    if (!playing || !data) return;
    let frame = 0;
    const perSecond = (data.hours / REPLAY_SECONDS) * speed;
    const tick = (now: number) => {
      const dt = last.current == null ? 0 : (now - last.current) / 1000;
      last.current = now;
      setHour((h) => {
        const next = Math.min(h + dt * perSecond, data.hours);
        if (next >= data.hours) setPlaying(false);
        return next;
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      last.current = null;
    };
  }, [playing, speed, data]);

  const stays = useMemo(() => new Map((data?.encounters ?? []).map((s) => [s.id, s])), [data]);

  const view = useMemo(() => {
    if (!data) return null;
    const past = data.events.filter((e) => e.t <= hour);
    const status = new Map<string, BedState>();
    for (const e of past) {
      if (e.type === "flag") status.set(e.encounter_id, "gap");
      if (e.type === "query_sent") status.set(e.encounter_id, "with_physician");
      if (e.type === "answered") status.set(e.encounter_id, e.resolved ? "resolved" : "open");
    }
    const beds: (Stay | null)[] = Array.from({ length: data.beds }, () => null);
    for (const s of data.encounters) if (s.admit <= hour && hour < s.discharge) beds[s.bed] = s;
    const answered = past.filter((e) => e.type === "answered");
    return {
      beds,
      status,
      feed: past.filter((e) => e.type !== "discharge" && e.type !== "admit").slice(-FEED_LENGTH).reverse(),
      inBeds: beds.filter(Boolean).length,
      gaps: past.filter((e) => e.type === "flag").length,
      sent: past.filter((e) => e.type === "query_sent").length,
      resolved: answered.filter((e) => e.resolved).length,
      drgCorrected: answered.filter((e) => e.resolved && e.drg_from !== e.drg_to).length,
    };
  }, [data, hour]);

  if (!data || !view) return <p className="text-slate-500">Loading the ward…</p>;

  const stat = (value: number, label: string, tone: string) => (
    <div className="px-4 py-3">
      <div className={`font-mono text-2xl ${tone}`}>{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Ward replay</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            {data.encounters.length} synthetic patients admitted over {data.admit_days} days to a {data.beds}-bed
            unit. Gaps are caught while the patient is still in the bed, at the first hour the evidence exists.
          </p>
        </div>
        <div className="font-mono text-3xl tracking-tight text-slate-900">{clock(hour)}</div>
      </section>

      <section className="flex flex-wrap items-center gap-3 rounded-xl bg-white p-3 ring-1 ring-slate-200">
        <button
          onClick={() => {
            if (hour >= data.hours) setHour(0);
            setPlaying(!playing);
          }}
          className="w-24 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          {playing ? "Pause" : hour >= data.hours ? "Replay" : "Play"}
        </button>
        <div className="flex gap-1" role="group" aria-label="Speed">
          {SPEEDS.map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`rounded-md px-2.5 py-1.5 text-sm ${speed === s ? "bg-teal-700 text-white" : "text-slate-600 hover:bg-slate-100"}`}
            >
              {s}x
            </button>
          ))}
        </div>
        <input
          type="range"
          min={0}
          max={data.hours}
          step={1}
          value={hour}
          onChange={(e) => setHour(Number(e.target.value))}
          aria-label="Time"
          className="flex-1 accent-teal-700"
        />
      </section>

      <section className="grid grid-cols-2 md:grid-cols-5 divide-x divide-slate-200 rounded-xl bg-white ring-1 ring-slate-200">
        {stat(view.inBeds, "Patients in beds", "text-slate-900")}
        {stat(view.gaps, "Gaps caught", "text-amber-700")}
        {stat(view.sent, "Queries sent", "text-violet-700")}
        {stat(view.resolved, "Resolved", "text-emerald-700")}
        {stat(view.drgCorrected, "Billing categories corrected", "text-slate-900")}
      </section>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <section>
          <div className="grid grid-cols-8 sm:grid-cols-10 lg:grid-cols-13 gap-1.5">
            {view.beds.map((stay, bed) => {
              const state: BedState = stay ? (view.status.get(stay.id) ?? "stable") : "empty";
              const tile = (
                <div
                  className={`flex h-12 flex-col justify-between rounded-md p-1 text-[10px] ring-1 transition-colors duration-500 ${BED_STYLE[state]}`}
                  title={stay ? `${stay.id}: ${stay.age} y ${stay.sex}, ${stay.reason}` : `Bed ${bed + 1}, empty`}
                >
                  <span className="opacity-60">{bed + 1}</span>
                  <span className="font-mono font-medium">{stay?.id ?? ""}</span>
                </div>
              );
              return stay && linkCharts ? (
                <Link key={bed} href={`/encounters/${stay.id}`}>
                  {tile}
                </Link>
              ) : (
                <div key={bed}>{tile}</div>
              );
            })}
          </div>
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-600">
            {LEGEND.map(([state, label]) => (
              <span key={state} className="flex items-center gap-1.5">
                <span className={`inline-block h-3 w-3 rounded-sm ring-1 ${BED_STYLE[state]}`} />
                {label}
              </span>
            ))}
          </div>
        </section>

        <aside className="rounded-xl bg-white p-4 ring-1 ring-slate-200">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Live feed</h2>
          <ol className="mt-3 space-y-3">
            {view.feed.map((e, i) => (
              <li key={`${e.t}-${e.type}-${e.encounter_id}-${i}`} className="text-sm leading-snug">
                <div className="font-mono text-[11px] text-slate-400">
                  {clock(e.t)} · {e.encounter_id}
                </div>
                <div className="text-slate-700">{describe(e, stays)}</div>
              </li>
            ))}
            {view.feed.length === 0 && <li className="text-sm text-slate-400">Press Play to start the replay.</li>}
          </ol>
        </aside>
      </div>
    </div>
  );
}
