"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type AuditRow } from "../lib/api";

const ACTION_LABEL: Record<string, string> = {
  approved_and_sent: "Approved and sent",
  edited_approved_and_sent: "Edited, approved and sent",
  rejected: "Rejected",
  answered: "Physician answered",
  flag_resolved: "Gap resolved",
  reset: "Demo reset",
};

export default function AuditPage() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.audit().then(setRows).catch(() => setRows([]));
  }, []);

  useEffect(load, [load]);

  async function reset() {
    setBusy(true);
    try {
      await api.reset();
      setConfirming(false);
      load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
          <p className="mt-1 text-sm text-slate-500">
            Every human decision and every physician answer, newest first. Append-only: a demo reset is logged,
            never erased.
          </p>
        </div>
        {confirming ? (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-slate-600">Remove all addenda and redraft every query?</span>
            <button disabled={busy} onClick={reset} className="rounded-lg bg-rose-700 px-3 py-1.5 text-white disabled:opacity-40">
              Yes, reset
            </button>
            <button onClick={() => setConfirming(false)} className="px-2 text-slate-500">
              Cancel
            </button>
          </div>
        ) : (
          <button onClick={() => setConfirming(true)} className="rounded-lg px-3 py-1.5 text-sm text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50">
            Reset demo
          </button>
        )}
      </section>

      <div className="rounded-xl bg-white ring-1 ring-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2.5 font-medium">Time</th>
              <th className="px-4 py-2.5 font-medium">Who</th>
              <th className="px-4 py-2.5 font-medium">Action</th>
              <th className="px-4 py-2.5 font-medium">Query</th>
              <th className="px-4 py-2.5 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(rows ?? []).map((r, i) => (
              <tr key={`${r.ts}-${i}`}>
                <td className="px-4 py-2.5 font-mono text-xs text-slate-500 whitespace-nowrap">
                  {new Date(r.ts).toLocaleString()}
                </td>
                <td className="px-4 py-2.5">{r.actor}</td>
                <td className="px-4 py-2.5 font-medium">{ACTION_LABEL[r.action] ?? r.action}</td>
                <td className="px-4 py-2.5 font-mono text-xs">{r.query_id}</td>
                <td className="px-4 py-2.5 text-slate-600 max-w-md truncate" title={r.detail}>
                  {r.detail}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows?.length === 0 && <p className="p-6 text-sm text-slate-500">No actions yet.</p>}
      </div>
    </div>
  );
}
