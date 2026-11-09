import Link from "next/link";

/** Shown in the hosted demo for screens that need the local Python API. */
export default function LocalOnly({ screen }: { screen: string }) {
  return (
    <div className="mx-auto max-w-xl rounded-xl bg-white p-8 text-center ring-1 ring-slate-200">
      <h1 className="text-lg font-semibold">The {screen} runs locally</h1>
      <p className="mt-2 text-sm text-slate-600">
        This hosted demo only replays precomputed results, so no visitor can change data or trigger an AI call.
        The full app, with the live rules check, physician inbox and audit log, runs from the repository.
      </p>
      <div className="mt-5 flex justify-center gap-3 text-sm">
        <Link href="/" className="rounded-lg bg-slate-900 px-4 py-2 text-white">
          Watch the ward replay
        </Link>
        <a href="https://github.com/nikhilcrypto0/wardsight" className="rounded-lg px-4 py-2 ring-1 ring-slate-300">
          View the source
        </a>
      </div>
    </div>
  );
}
