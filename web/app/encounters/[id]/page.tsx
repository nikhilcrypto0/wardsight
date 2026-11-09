import { Suspense } from "react";
import LocalOnly from "../../components/LocalOnly";
import { IS_PUBLIC } from "../../lib/mode";
import EncounterView from "./EncounterView";

// The encounter id is only known at request time; with Cache Components the
// client view that reads it must sit inside a Suspense boundary.
export default function EncounterPage() {
  if (IS_PUBLIC) return <LocalOnly screen="patient chart" />;
  return (
    <Suspense fallback={<p className="text-slate-500">Loading chart…</p>}>
      <EncounterView />
    </Suspense>
  );
}
