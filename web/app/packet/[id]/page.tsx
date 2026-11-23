import { Suspense } from "react";
import PacketView from "./PacketView";

// The query id is only known at request time; with Cache Components the client view that
// reads it must sit inside a Suspense boundary.
export default function PacketPage() {
  return (
    <Suspense fallback={<p className="text-slate-500">Loading packet…</p>}>
      <PacketView />
    </Suspense>
  );
}
