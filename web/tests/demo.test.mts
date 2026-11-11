// The hosted demo's browser backend must behave like the Python engine.
// demo-expected.json is written by `uv run wardsight-demo` after it approves every query and
// lets the simulated physician answer, on a copy of the real database.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { beforeEach, test } from "node:test";
import { demoApi } from "../app/lib/demo.ts";

const publicDir = new URL("../public", import.meta.url);
globalThis.fetch = (async (path: string) => {
  try {
    const body = readFileSync(new URL(`.${path}`, publicDir + "/"), "utf8");
    return new Response(body, { status: 200 });
  } catch {
    return new Response("{}", { status: 404 });
  }
}) as typeof fetch;

const expected = JSON.parse(readFileSync(new URL("./demo-expected.json", import.meta.url), "utf8"));

beforeEach(async () => {
  await demoApi.reset();
});

test("D0011: approve, physician answers Sepsis, billing category 690 -> 872", async () => {
  const chart = await demoApi.encounter("D0011");
  const query = chart.queries[0];
  assert.equal(query.status, "pending_review");
  assert.equal(chart.flags[0].condition, "sepsis");

  await assert.rejects(demoApi.simulate(query.query_id), /needs sent/);
  await assert.rejects(demoApi.approve(query.query_id, "Does this patient have sepsis?"), /names the diagnosis/);
  await demoApi.approve(query.query_id);
  assert.equal((await demoApi.simulate(query.query_id)).status, "resolved");

  const after = await demoApi.encounter("D0011");
  assert.equal(after.drg.drg, 872);
  assert.equal(after.flags.length, 0);
  assert.match(after.notes.at(-1)!.text, /^ADDENDUM in response to documentation query: sepsis\. Agree/);
  const actions = (await demoApi.audit()).map((a) => a.action);
  assert.deepEqual(actions.slice(0, 3), ["flag_resolved", "answered", "approved_and_sent"]);
});

test("a physician who disagrees leaves the gap open", async () => {
  const query = (await demoApi.encounter("D0011")).queries[0];
  await demoApi.approve(query.query_id);
  assert.equal((await demoApi.answer(query.query_id, 1, "Source control only")).status, "answered");
  const chart = await demoApi.encounter("D0011");
  assert.equal(chart.drg.drg, 690);
  assert.equal(chart.flags.length, 1);
});

test("working every query lands on the engine's ward totals", async () => {
  for (const row of await demoApi.worklist()) {
    await demoApi.approve(row.query_id);
    await demoApi.simulate(row.query_id);
  }
  const summary = await demoApi.summary();
  assert.deepEqual(summary.queries, expected.statuses);
  assert.deepEqual(summary.open_flags, expected.open_flags);
  assert.deepEqual(await demoApi.leadership(), expected.leadership);
  assert.deepEqual((await demoApi.ur()).counts, expected.ur_counts);
});
