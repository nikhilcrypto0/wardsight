"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Packet } from "../../lib/api";
import { KIND } from "../../lib/labels";

const ACTION: Record<string, string> = {
  approved_and_sent: "Approved and sent",
  edited_approved_and_sent: "Edited, approved and sent",
  answered: "Physician answered",
  flag_resolved: "Gap resolved",
  rejected: "Rejected",
};

function when(ts?: string | null): string {
  return ts ? new Date(ts).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "—";
}

function Section({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="break-inside-avoid border-t border-slate-200 pt-5">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
        {n}. {title}
      </h2>
      <div className="mt-2 text-sm text-slate-800">{children}</div>
    </section>
  );
}

/** Everything an auditor or payer asks about one answered query, printable on its own. */
export default function PacketView() {
  const { id } = useParams<{ id: string }>();
  const [p, setP] = useState<Packet | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.packet(id).then(setP).catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load"));
  }, [id]);

  if (error) return <p className="text-rose-700">{error}</p>;
  if (!p) return <p className="text-slate-500">Loading packet…</p>;

  const delta =
    p.outcome.weight_before != null && p.outcome.weight_after != null
      ? p.outcome.weight_after - p.outcome.weight_before
      : null;

  return (
    <article className="mx-auto max-w-3xl space-y-6 rounded-xl bg-white p-8 ring-1 ring-slate-200 print:ring-0">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-teal-700">Audit-defense packet</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">
            {p.encounter_id} · {p.condition_name}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {p.patient.age}-year-old {p.patient.sex}, admitted for {p.patient.reason_for_admission},{" "}
            {p.patient.los_days}-day stay · alert: {KIND[p.alert]} · query {p.query_id}
          </p>
        </div>
        <div className="flex gap-2 print:hidden">
          <Link href={`/encounters/${p.encounter_id}`} className="rounded-lg px-3 py-1.5 text-sm ring-1 ring-slate-300">
            Open chart
          </Link>
          <button onClick={() => window.print()} className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white">
            Print / save as PDF
          </button>
        </div>
      </header>

      <Section n={1} title="Clinical evidence in the record">
        <ul className="list-disc space-y-0.5 pl-5 font-mono text-[13px]">
          {p.evidence.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      </Section>

      <Section n={2} title="The published rule it meets">
        <div className="space-y-3">
          {p.rules.map((r) => (
            <div key={r.key}>
              <div className="font-medium">{r.condition}</div>
              <div>{r.rule}</div>
              <div className="text-xs text-slate-500">Source: {r.source}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section n={3} title="The question the physician saw">
        <blockquote className="rounded-lg bg-slate-50 p-3">{p.query.stem}</blockquote>
        <ol className="mt-2 list-decimal space-y-0.5 pl-5">
          {p.query.options.map((o) => (
            <li key={o} className={o === p.answer.option ? "font-semibold" : ""}>
              {o}
              {o === p.answer.option ? "  (chosen)" : ""}
            </li>
          ))}
        </ol>
        <p className="mt-2 text-xs text-slate-500">
          Answer options were chosen by code; the {p.query.drafter === "openai" ? "AI" : "template"} wrote only the
          question sentence.
        </p>
      </Section>

      <Section n={4} title="Compliant-query check">
        {p.query.rules_check.ok ? (
          <p>
            <span className="font-medium text-emerald-700">Passed.</span> No leading wording, the new diagnosis is not
            named in the question, no billing talk, enough clinical indicators, and every number matches the chart.
          </p>
        ) : (
          <ul className="list-disc pl-5 text-rose-700">
            {p.query.rules_check.problems.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        )}
        <p className="mt-1 text-xs text-slate-500">Checked against: {p.query.standard}. Re-run on the exact text sent.</p>
      </Section>

      <Section n={5} title="Human approval and physician answer">
        <dl className="grid grid-cols-[10rem_1fr] gap-y-1">
          <dt className="text-slate-500">Approved by</dt>
          <dd>
            {p.approval ? `${p.approval.by}, ${when(p.approval.at)}${p.approval.edited ? " (edited before sending)" : ""}` : "—"}
          </dd>
          <dt className="text-slate-500">Answered by</dt>
          <dd>
            {p.answer.by ?? "—"}, {when(p.answer.at)}
          </dd>
          <dt className="text-slate-500">Answer</dt>
          <dd>
            {p.answer.option}
            {p.answer.comment ? ` · “${p.answer.comment}”` : ""}
          </dd>
          <dt className="text-slate-500">Addendum</dt>
          <dd>{p.addendum ?? "None (the answer did not change the record)"}</dd>
        </dl>
      </Section>

      <Section n={6} title="Outcome">
        <p>
          {p.outcome.status === "resolved" ? "Gap resolved." : "Answered; the gap is still open."} Billing category
          (MS-DRG) <span className="font-mono">{p.outcome.drg_before}</span> to{" "}
          <span className="font-mono">{p.outcome.drg_after}</span>
          {delta != null && (
            <>
              , relative weight <span className="font-mono">{p.outcome.weight_before?.toFixed(4)}</span> to{" "}
              <span className="font-mono">{p.outcome.weight_after?.toFixed(4)}</span> (
              <span className="font-mono">{delta >= 0 ? "+" : ""}{delta.toFixed(4)}</span>)
            </>
          )}
          .
        </p>
      </Section>

      <Section n={7} title="Audit trail (append-only)">
        <table className="w-full text-[13px]">
          <tbody className="divide-y divide-slate-100">
            {p.trail.map((t, i) => (
              <tr key={i} className="align-top">
                <td className="py-1.5 pr-3 font-mono text-xs text-slate-500 whitespace-nowrap">{when(t.ts)}</td>
                <td className="py-1.5 pr-3 whitespace-nowrap">{t.actor}</td>
                <td className="py-1.5 pr-3 font-medium whitespace-nowrap">{ACTION[t.action] ?? t.action}</td>
                <td className="py-1.5 text-slate-600">{t.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <p className="border-t border-slate-200 pt-4 text-xs text-slate-400">
        Synthetic data only. No real patients. Demo, not for clinical use.
      </p>
    </article>
  );
}
