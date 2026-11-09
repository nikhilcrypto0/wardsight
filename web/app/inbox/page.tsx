"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import LocalOnly from "../components/LocalOnly";
import { api, type InboxItem } from "../lib/api";
import { IS_PUBLIC } from "../lib/mode";
import { CONDITION, DrgShift, StatusBadge } from "../lib/labels";

function OpenQuery({ item, onChanged }: { item: InboxItem; onChanged: () => void }) {
  const [choice, setChoice] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <fieldset className="space-y-3">
      <legend className="sr-only">Answer options</legend>
      <div className="grid gap-1.5">
        {item.options.map((o, i) => (
          <label
            key={o}
            className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm ring-1 ${
              choice === i ? "bg-teal-50 ring-teal-400" : "ring-slate-200 hover:bg-slate-50"
            }`}
          >
            <input type="radio" name={item.query_id} checked={choice === i} onChange={() => setChoice(i)} />
            {o}
          </label>
        ))}
      </div>
      <input
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Optional comment"
        aria-label="Optional comment"
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
      />
      {error && <p className="text-sm text-rose-700">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <button
          disabled={busy || choice === null}
          onClick={() => choice !== null && run(() => api.answer(item.query_id, choice, comment))}
          className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-40"
        >
          Answer as physician
        </button>
        <button
          disabled={busy}
          onClick={() => run(() => api.simulate(item.query_id))}
          className="rounded-lg px-4 py-2 text-sm text-violet-700 ring-1 ring-violet-300 hover:bg-violet-50"
        >
          Let the simulated physician reply
        </button>
      </div>
    </fieldset>
  );
}

export default function InboxPage() {
  return IS_PUBLIC ? <LocalOnly screen="physician inbox" /> : <InboxScreen />;
}

function InboxScreen() {
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .inbox()
      .then(setItems)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load the inbox"));
  }, []);

  useEffect(load, [load]);

  if (error) return <p className="text-rose-700">{error}</p>;
  if (!items) return <p className="text-slate-500">Loading inbox…</p>;

  const waiting = items.filter((i) => i.status === "sent");
  const done = items.filter((i) => i.status !== "sent");

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">Physician inbox</h1>
        <p className="mt-1 text-sm text-slate-500">
          Queries a CDI reviewer approved. Answer one yourself, or let the simulated physician reply. Each answer
          becomes a note addendum, and the chart is rescanned.
        </p>
      </section>

      {waiting.length === 0 && (
        <p className="rounded-xl bg-white ring-1 ring-slate-200 p-6 text-sm text-slate-500">
          No queries waiting. Approve one from the <Link href="/" className="text-teal-700 underline">worklist</Link>.
        </p>
      )}

      {waiting.map((item) => (
        <article key={item.query_id} className="rounded-xl bg-white ring-1 ring-slate-200 p-5 space-y-4">
          <header className="flex flex-wrap items-center gap-2 text-sm">
            <Link href={`/encounters/${item.encounter_id}`} className="font-mono text-blue-700 hover:underline">
              {item.encounter_id}
            </Link>
            <span className="text-slate-500">
              {item.age} y {item.sex}, {item.reason_for_admission}
            </span>
            <span className="ml-auto">
              <StatusBadge status={item.status} />
            </span>
          </header>
          <p className="text-sm leading-relaxed">{item.stem}</p>
          <OpenQuery item={item} onChanged={load} />
        </article>
      ))}

      {done.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Answered</h2>
          {done.map((item) => (
            <div key={item.query_id} className="flex flex-wrap items-center gap-3 rounded-lg bg-white ring-1 ring-slate-200 px-4 py-3 text-sm">
              <Link href={`/encounters/${item.encounter_id}`} className="font-mono text-blue-700 hover:underline">
                {item.encounter_id}
              </Link>
              <span className="font-medium">{CONDITION[item.condition]}</span>
              <span className="text-slate-600">→ {item.answer}</span>
              <span className="ml-auto flex items-center gap-3">
                <span className="text-xs text-slate-500">
                  DRG <DrgShift from={item.drg_before} to={item.drg_after} />
                </span>
                <StatusBadge status={item.status} />
              </span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
