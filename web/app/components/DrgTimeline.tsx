import type { DrgStep } from "../lib/api";

const SOURCE: Record<string, string> = {
  admission: "Admission",
  history_and_physical: "History and physical",
  progress_note: "Progress note",
  discharge_summary: "Discharge summary",
  addendum: "Physician addendum",
};

/** Working DRG during the stay vs final DRG at discharge, and which note changed it. */
export default function DrgTimeline({ steps }: { steps: DrgStep[] }) {
  if (!steps?.length) return null;
  const final = steps[steps.length - 1];
  const firstDocumented = steps.find((s) => s.source !== "admission") ?? steps[0];
  return (
    <section className="rounded-xl bg-white p-5 ring-1 ring-slate-200">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Billing category over the stay</h2>
        <span className="text-xs text-slate-500">
          Working DRG <span className="font-mono">{firstDocumented.drg}</span> → final{" "}
          <span className="font-mono font-semibold text-slate-900">{final.drg}</span>
        </span>
      </div>
      <ol className="mt-4 space-y-3 border-l border-slate-200 pl-4">
        {steps.map((s, i) => {
          const changed = i > 0 && s.drg !== steps[i - 1].drg;
          return (
            <li key={`${s.source}-${s.hour}-${i}`} className="relative">
              <span
                className={`absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full ${
                  changed ? "bg-teal-600" : s.open_gaps ? "bg-amber-400" : "bg-slate-300"
                }`}
              />
              <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
                <span className="font-medium">{SOURCE[s.source] ?? s.source}</span>
                <span className="text-xs text-slate-500">day {s.day}</span>
                <span className="ml-auto font-mono">
                  {s.drg}
                  {s.severity !== "NONE" && <span className="ml-1 text-xs text-slate-500">{s.severity}</span>}
                </span>
              </div>
              {(s.added.length > 0 || s.removed.length > 0) && (
                <p className="text-xs text-slate-600">
                  {s.added.map((c) => `+ ${c.name}`).join("; ")}
                  {s.added.length > 0 && s.removed.length > 0 ? "; " : ""}
                  {s.removed.map((c) => `− ${c.name}`).join("; ")}
                  {changed ? ` → ${s.description}` : ""}
                </p>
              )}
              {s.open_gaps > 0 && s.potential_drg !== s.drg && (
                <p className="text-xs text-amber-800">
                  {s.open_gaps} open gap{s.open_gaps > 1 ? "s" : ""}: if resolved, DRG {s.potential_drg}
                </p>
              )}
            </li>
          );
        })}
      </ol>
      <p className="mt-3 text-xs text-slate-500">
        Regrouped after every note from what the notes document so far. Amber: a gap was open at that point.
      </p>
    </section>
  );
}
