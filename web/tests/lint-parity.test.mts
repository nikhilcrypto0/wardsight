// The browser rules check must agree with the Python one, case for case.
// Cases come from `uv run wardsight-demo` (real dev queries plus edits a reviewer might make).
// Run: npm test   (Node 22+ runs this TypeScript file directly)

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { lintQuery } from "../app/lib/lint.ts";

interface Case {
  stem: string;
  options: string[];
  indicators: string[];
  condition: string;
  kind: string;
  ok: boolean;
  problems: string[];
}

const read = (path: string) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const cases: Case[] = read("./lint-cases.json");
const targets: Record<string, string[]> = read("../public/demo/index.json").lint_targets;

test(`browser rules check matches Python on ${cases.length} cases`, () => {
  assert.ok(cases.length > 1000);
  assert.ok(cases.some((c) => c.ok) && cases.some((c) => !c.ok));
  for (const c of cases) {
    assert.deepEqual(lintQuery({ ...c, targets }), { ok: c.ok, problems: c.problems }, c.stem.slice(0, 120));
  }
});
