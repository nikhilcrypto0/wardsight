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
  unspecified: { label: "Not fully specified", expect: "Vague term ('CHF', 'anemia') where the evidence is specific: must flag it" },
  unspecified_near: { label: "Vague, not specific", expect: "Vague term and the evidence does not support more: must stay quiet" },
  conflicting: { label: "Conflicting notes", expect: "One note states it, a later note rules it out: must flag it" },
  conflict_near: { label: "Stated, then resolved", expect: "A change over time, not a conflict: must stay quiet" },
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
            <span className="font-medium">Free-form wording.</span> The scores above use template notes. With all 234
            development charts rewritten by an AI model (gpt-5.4-mini, run on 2026-11-23) the engine scored the same,
            95 of 95 with no false alarms. Those AI notes used set wording per diagnosis. Real-world wording
            (&ldquo;AKI&rdquo;, &ldquo;r/o sepsis&rdquo;, &ldquo;likely&rdquo;, typos such as &ldquo;sespis&rdquo;)
            scored 95 of 95 with no false alarms on template notes (the earlier note reader: 83 of 95 with 16 false
            alarms) and 95 of 95 on AI-written notes in that style, on 233 of 234 charts. How the AI notes were
            made: 295 drafts, 60 rejected by the note check (which compares the planned wording with the note text
            only, never the engine) and redrafted. Chart D0221 never got an accepted draft (rejected 3 times in each
            of two runs) and kept its template notes. Its wording must stay in the admission note, and the
            copy-forward style most likely carried it into later notes; reasons were not recorded then and are now. D0109 and D0234 were redrafted once after the check
            was tightened; that choice was made by the check, before any scoring. Open question for a clinician: is
            a hedged diagnosis ruled out by discharge (&ldquo;concern for AKI&rdquo;, then &ldquo;no AKI&rdquo;)
            conflicting documentation? The coding-side view: ICD-10-CM II.H applies to uncertain diagnoses at the
            time of discharge, so one ruled out by then is not coded and reads as a progression, not a conflict.
            No clinician has reviewed the rules yet.
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
