import type { Metadata } from "next";
import Link from "next/link";
import evaluation from "../../public/demo/evaluation.json";

export const metadata: Metadata = {
  title: "Evaluation · WardSight",
  description: "How WardSight's detection and query rules are tested, and what is not proven yet.",
};

// Written by `uv run wardsight-demo` from the real benchmark run, the drafted queries and the
// constants the evidence rules use, so this page cannot drift from the engine.
const GROUPS: Record<string, { label: string; expect: string }> = {
  missing: { label: "Missing diagnosis", expect: "Evidence met, never documented: must flag it" },
  unsupported: { label: "Unsupported diagnosis", expect: "Documented, evidence absent: must flag it" },
  correct: { label: "Correctly documented", expect: "Evidence and notes agree: must stay quiet" },
  near_miss: { label: "Near-miss", expect: "Just below the published threshold: must stay quiet" },
  confounder: { label: "Confounder", expect: "Chronic kidney disease, high but stable creatinine: must stay quiet" },
  routine: { label: "Routine admission", expect: "Nothing to find: must stay quiet" },
};

const { benchmark: b, queries: q, rules, heldout_charts, parity_cases } = evaluation;

function Headline({ value, label, note }: { value: string; label: string; note: string }) {
  return (
    <div className="px-5 py-5 border-b md:border-b-0 md:border-r border-slate-200 last:border-0">
      <div className="font-mono text-3xl tracking-tight text-slate-900">{value}</div>
      <div className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <p className="mt-2 text-xs text-slate-500">{note}</p>
    </div>
  );
}

export default function EvaluationPage() {
  return (
    <div className="space-y-10">
      <section className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">How we know it works, and what is not proven yet</h1>
        <p className="mt-2 text-sm text-slate-600">
          Detection is plain code, so it can be tested like code. The test ward has an answer key the engine is not
          allowed to read, built to include the cases that fool a careless rule: values just under a threshold and
          patients whose chronic disease mimics an acute one.
        </p>
      </section>

      <section className="grid md:grid-cols-4 rounded-xl bg-white ring-1 ring-slate-200">
        <Headline
          value={`${b.caught}/${b.planted}`}
          label="Planted gaps caught"
          note="Right condition and right gap type, on the development ward."
        />
        <Headline
          value={String(b.false_alarms)}
          label="False alarms"
          note={`Across ${b.quiet_charts} charts that should raise nothing.`}
        />
        <Headline
          value={`${q.passed_check}/${q.drafted}`}
          label="Queries pass the rules check"
          note="ACDIS/AHIMA 2022: no leading wording, no billing talk, no invented numbers."
        />
        <Headline
          value={parity_cases.toLocaleString("en-US")}
          label="Browser = engine cases"
          note="This site's rules check gives the same answer as the Python one on every case."
        />
      </section>

      <section className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3 rounded-xl bg-white ring-1 ring-slate-200 overflow-hidden">
          <h2 className="px-5 pt-5 text-sm font-semibold">Development ward, by test group</h2>
          <p className="px-5 pt-1 text-xs text-slate-500">{b.planted + b.quiet_charts} synthetic inpatient stays.</p>
          <table className="mt-3 w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-5 py-2 font-medium">Group</th>
                <th className="px-3 py-2 font-medium">What a correct engine does</th>
                <th className="px-3 py-2 font-medium text-right">Charts</th>
                <th className="px-5 py-2 font-medium text-right">Correct</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {b.by_group.map((g) => (
                <tr key={g.group}>
                  <td className="px-5 py-2.5 font-medium">{GROUPS[g.group]?.label ?? g.group}</td>
                  <td className="px-3 py-2.5 text-slate-600">{GROUPS[g.group]?.expect}</td>
                  <td className="px-3 py-2.5 text-right font-mono">{g.charts}</td>
                  <td className="px-5 py-2.5 text-right font-mono text-emerald-700">{g.correct}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="lg:col-span-2 rounded-xl bg-white p-5 ring-1 ring-slate-200">
          <h2 className="text-sm font-semibold">Why the test can be trusted</h2>
          <ul className="mt-3 space-y-3 text-sm text-slate-600">
            <li>
              <span className="font-medium text-slate-900">Two separate programs.</span> One writes the patients and the
              answer key; the detection rules were written separately and are blocked, by an automated test, from
              importing the generator or reading the key.
            </li>
            <li>
              <span className="font-medium text-slate-900">Hard cases on purpose.</span> Near-misses and confounders
              are where simple rules raise false alarms, and false alarms are what make clinicians ignore a tool.
            </li>
            <li>
              <span className="font-medium text-slate-900">A sealed held-out ward.</span> {heldout_charts} more stays
              that no rule was tuned on. It can be scored once; a second attempt is refused, so the final number cannot
              be massaged.
            </li>
          </ul>
        </div>
      </section>

      <section className="rounded-xl bg-white ring-1 ring-slate-200 overflow-hidden">
        <h2 className="px-5 pt-5 text-sm font-semibold">The clinical rules, and where each threshold comes from</h2>
        <p className="px-5 pt-1 text-xs text-slate-500">
          Every flag on a chart lists the exact values and hours that met these rules.
        </p>
        <table className="mt-3 w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-5 py-2 font-medium">Condition</th>
              <th className="px-3 py-2 font-medium">Evidence the rule requires</th>
              <th className="px-5 py-2 font-medium">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 align-top">
            {rules.map((r) => (
              <tr key={r.condition}>
                <td className="px-5 py-3 font-medium whitespace-nowrap">{r.condition}</td>
                <td className="px-3 py-3 text-slate-700">{r.rule}</td>
                <td className="px-5 py-3 text-slate-500">{r.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="rounded-xl bg-amber-50 p-5 ring-1 ring-amber-200">
        <h2 className="text-sm font-semibold text-amber-900">Not proven yet</h2>
        <ul className="mt-3 grid gap-3 text-sm text-amber-900/90 md:grid-cols-2">
          <li>
            <span className="font-medium">Messy notes.</span> These scores use notes written from templates, with clean
            wording. Real notes hedge, abbreviate and copy forward. The next test uses LLM-written notes with that
            variety, scored on the same answer key.
          </li>
          <li>
            <span className="font-medium">The held-out ward.</span> Not scored yet; it is run once, after the rules
            are final.
          </li>
          <li>
            <span className="font-medium">Real charts.</span> All patients are synthetic. The FHIR reader works on
            Epic-format data, but no rule has been validated on real records.
          </li>
          <li>
            <span className="font-medium">The physician.</span> Answers here come from a rule-based simulator, not
            clinicians. Billing weights cover the 16 MS-DRGs this ward uses (CMS FY2027, v44).
          </li>
        </ul>
      </section>

      <p className="text-sm text-slate-500">
        See it on a single patient:{" "}
        <Link href="/encounters/D0011" className="text-teal-700 underline">
          D0011, sepsis missed on a urinary tract infection admission
        </Link>
        .
      </p>
    </div>
  );
}
