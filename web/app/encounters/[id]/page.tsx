import { Suspense } from "react";
import EncounterView from "./EncounterView";

// The encounter id is only known at request time; with Cache Components the
// client view that reads it must sit inside a Suspense boundary.
export default function EncounterPage() {
  return (
    <Suspense fallback={<p className="text-slate-500">Loading chart…</p>}>
      <EncounterView />
    </Suspense>
  );
}
