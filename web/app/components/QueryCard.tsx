"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Query } from "../lib/api";
import { CONDITION, DrgShift, KindBadge, StatusBadge } from "../lib/labels";

interface QueryCardProps {
  query: Query;
  onChanged: () => void;
}

const LINT_DELAY_MS = 400;

/** Reviewer's view of one drafted query: edit, live rules check, approve or reject. */
export default function QueryCard({ query, onChanged }: QueryCardProps) {
  const editable = query.status === "pending_review" || query.status === "needs_rewrite";
  const [stem, setStem] = useState(query.stem);
  const [lint, setLint] = useState<{ ok: boolean; problems: string[] }>({
    ok: query.problems.length === 0,
    problems: query.problems,
  });
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editable) return;
    const timer = setTimeout(() => {
      api.lint(query.query_id, stem).then(setLint).catch(() => undefined);
    }, LINT_DELAY_MS);
    return () => clearTimeout(timer);
  }, [stem, editable, query.query_id]);

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

  const edited = stem.trim() !== query.stem.trim();

  return (
    <article className="rounded-xl bg-white ring-1 ring-slate-200 p-5 space-y-4">
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">Query: {CONDITION[query.condition]}</h3>
        <KindBadge kind={query.kind} />
        <span className="ml-auto">
          <StatusBadge status={query.status} />
        </span>
      </header>

      {editable ? (
        <div className="space-y-2">
          <label htmlFor={`stem-${query.query_id}`} className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Question to the physician (editable)
          </label>
          <textarea
            id={`stem-${query.query_id}`}
            value={stem}
            onChange={(e) => setStem(e.target.value)}
            rows={5}
            className="w-full rounded-lg border border-slate-300 p-3 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-teal-600"
          />
          <div
            role="status"
            className={`rounded-lg px-3 py-2 text-sm ${lint.ok ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}
          >
            {lint.ok ? (
              "Passes the compliant query rules check (ACDIS/AHIMA)."
            ) : (
              <ul className="list-disc pl-5 space-y-0.5">
                {lint.problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : (
        <p className="text-sm leading-relaxed text-slate-800">{query.stem}</p>
      )}

      <div>
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Answer options (set by code)</div>
        <ul className="mt-1.5 grid gap-1 text-sm">
          {query.options.map((o) => (
            <li key={o} className={`rounded-md px-3 py-1.5 ${query.answer === o ? "bg-teal-50 ring-1 ring-teal-300" : "bg-slate-50"}`}>
              {o}
            </li>
          ))}
        </ul>
      </div>

      {query.answer && (
        <div className="rounded-lg bg-slate-50 p-3 text-sm space-y-1">
          <div>
            <span className="font-medium">{query.answered_by}:</span> {query.answer}
          </div>
          {query.answer_comment && <div className="text-slate-600">“{query.answer_comment}”</div>}
          <div className="text-slate-600">
            DRG <DrgShift from={query.drg_before} to={query.drg_after} />
          </div>
        </div>
      )}

      {query.status === "sent" && (
        <p className="text-sm text-violet-700">
          Waiting in the <Link href="/inbox" className="underline">physician inbox</Link>.
        </p>
      )}

      {error && <p className="text-sm text-rose-700">{error}</p>}

      {editable && !rejecting && (
        <div className="flex gap-2">
          <button
            disabled={busy || !lint.ok}
            onClick={() => run(() => api.approve(query.query_id, edited ? stem : undefined))}
            className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-40"
          >
            {edited ? "Approve edit and send" : "Approve and send"}
          </button>
          <button
            disabled={busy}
            onClick={() => setRejecting(true)}
            className="rounded-lg px-4 py-2 text-sm text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50"
          >
            Reject
          </button>
        </div>
      )}

      {rejecting && (
        <div className="flex gap-2">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason for not sending"
            aria-label="Reason for not sending"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            disabled={busy || reason.trim().length < 3}
            onClick={() => run(() => api.reject(query.query_id, reason))}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm text-white disabled:opacity-40"
          >
            Confirm reject
          </button>
          <button onClick={() => setRejecting(false)} className="px-3 text-sm text-slate-500">
            Cancel
          </button>
        </div>
      )}
    </article>
  );
}
