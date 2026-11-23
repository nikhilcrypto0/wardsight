"""End-to-end workflow through the HTTP API: review, send, answer, addendum, rescan, audit, reset."""

from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path

import duckdb
import pytest
from counts import DEV_CHARTS, DEV_FLAGS
from fastapi.testclient import TestClient

from wardsight.api.app import create_app
from wardsight.api.reports import response_times
from wardsight.engine.scan import scan
from wardsight.factory import run as build_ward
from wardsight.notes.template import write_template_notes
from wardsight.queries.draft import template_drafter
from wardsight.queries.run import draft_all
from wardsight.reload import load_encounters


@pytest.fixture(scope="module")
def base_db(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("api-ward")
    build_ward(out, seed=33, synthea_dir=None)
    db = out / "wardsight.duckdb"
    with duckdb.connect(str(db)) as con:
        write_template_notes(con, load_encounters(con), seed=33)
        scan(con, "dev")
        draft_all(con, "dev", template_drafter, "template", 1)
    return db


@pytest.fixture()
def client(base_db: Path, tmp_path: Path) -> TestClient:
    db = tmp_path / "wardsight.duckdb"  # every test gets its own fresh copy of the ward
    shutil.copy(base_db, db)
    return TestClient(create_app(db))


def first(client: TestClient, condition: str, kind: str) -> dict:
    return next(r for r in client.get("/api/worklist").json() if r["condition"] == condition and r["kind"] == kind)


def test_worklist_and_summary(client):
    rows = client.get("/api/worklist").json()
    assert len(rows) == DEV_FLAGS and {r["status"] for r in rows} == {"pending_review"}
    assert client.get("/api/summary").json()["queries"] == {"pending_review": DEV_FLAGS}
    for r in rows:  # every open gap carries a priority that is exactly the sum of its shown parts
        assert 0 <= r["priority"] <= 100
        assert r["priority"] == sum(p["points"] for p in r["priority_parts"])
    kinds = {r["kind"] for r in rows if r["priority"] >= 50}
    assert {"missing_dx", "unsupported_dx"} <= kinds  # unsupported diagnoses rank high too


def test_heldout_charts_are_never_served(client):
    assert client.get("/api/encounters/H0001").status_code == 404


def test_confirmed_missing_dx_resolves_and_moves_drg(client):
    q = first(client, "sepsis", "missing_dx")
    assert client.post(f"/api/queries/{q['query_id']}/answer", json={"option_index": 0}).status_code == 409
    assert client.post(f"/api/queries/{q['query_id']}/approve", json={}).json() == {"status": "sent"}
    assert client.post(f"/api/queries/{q['query_id']}/approve", json={}).status_code == 409

    r = client.post(f"/api/queries/{q['query_id']}/answer", json={"option_index": 0, "comment": "Agree."})
    assert r.json() == {"status": "resolved"}
    chart = client.get(f"/api/encounters/{q['encounter_id']}").json()
    assert not [f for f in chart["flags"] if f["condition"] == "sepsis"]
    assert chart["drg"]["principal"] == "A41.9"
    assert any(n["type"] == "addendum" for n in chart["notes"])
    answered = next(x for x in chart["queries"] if x["query_id"] == q["query_id"])
    assert answered["drg_before"] != answered["drg_after"]
    row = next(r for r in client.get("/api/worklist").json() if r["query_id"] == q["query_id"])
    assert row["priority"] is None  # a closed gap drops out of the ranking


def test_ruled_out_unsupported_dx_resolves(client):
    q = first(client, "aki", "unsupported_dx")
    client.post(f"/api/queries/{q['query_id']}/approve", json={})
    assert client.post(f"/api/queries/{q['query_id']}/answer", json={"option_index": 1}).json() == {
        "status": "resolved"}


def test_undetermined_answer_leaves_flag_open(client):
    q = first(client, "hyponatremia", "missing_dx")
    client.post(f"/api/queries/{q['query_id']}/approve", json={})
    options = client.get(f"/api/encounters/{q['encounter_id']}").json()["queries"][0]["options"]
    status = client.post(f"/api/queries/{q['query_id']}/answer",
                         json={"option_index": len(options) - 1}).json()["status"]
    assert status == "answered"


def test_edited_query_must_pass_the_rules_check(client):
    q = first(client, "sepsis", "missing_dx")
    bad = "Please document sepsis, it raises the DRG?"
    lint = client.post("/api/lint", json={"query_id": q["query_id"], "stem": bad}).json()
    assert not lint["ok"] and len(lint["problems"]) >= 2
    r = client.post(f"/api/queries/{q['query_id']}/approve", json={"stem": bad})
    assert r.status_code == 409 and "leading" in r.json()["detail"]
    assert first(client, "sepsis", "missing_dx")["status"] == "pending_review"


def test_ur_and_leadership_reflect_resolved_queries(client):
    before = client.get("/api/leadership").json()
    ur = client.get("/api/ur").json()
    assert sum(ur["counts"].values()) == DEV_CHARTS
    q = first(client, "sepsis", "missing_dx")
    client.post(f"/api/queries/{q['query_id']}/approve", json={})
    client.post(f"/api/queries/{q['query_id']}/answer", json={"option_index": 0})
    after = client.get("/api/leadership").json()
    assert after["case_mix"]["current"] > before["case_mix"]["current"]
    assert after["case_mix"]["first_documented"] == before["case_mix"]["first_documented"]
    assert after["queries"]["resolved"] == 1 and after["queries"]["response_rate"] == 1.0
    responses = after["responses"]
    assert responses["median_hours_to_answer"] == 0.0  # answered seconds after it was sent
    assert responses["by_physician"] == [{"physician": "Attending physician", "answered": 1, "agreed": 1,
                                          "agreement_rate": 1.0}]
    assert responses["stale"] == []


def test_unanswered_query_goes_stale_after_48_hours(client, tmp_path):
    q = first(client, "sepsis", "missing_dx")
    client.post(f"/api/queries/{q['query_id']}/approve", json={})
    with duckdb.connect(str(tmp_path / "wardsight.duckdb")) as con:
        sent_at = con.execute("SELECT max(ts) FROM ops.audit").fetchone()[0]
        assert response_times(con, now=sent_at + timedelta(hours=47))["stale"] == []
        stale = response_times(con, now=sent_at + timedelta(hours=50))["stale"]
    assert [(r["query_id"], r["hours_waiting"]) for r in stale] == [(q["query_id"], 50.0)]


def test_reject_simulate_audit_and_reset(client):
    rejected, sent = first(client, "arf", "missing_dx"), first(client, "abla", "missing_dx")
    client.post(f"/api/queries/{rejected['query_id']}/reject", json={"reason": "Already discussed on rounds"})
    client.post(f"/api/queries/{sent['query_id']}/approve", json={})
    status = client.post(f"/api/queries/{sent['query_id']}/simulate").json()["status"]
    assert status in ("resolved", "answered")
    assert len(client.get("/api/inbox").json()) == 1
    actions_logged = [a["action"] for a in client.get("/api/audit").json()]
    assert {"rejected", "approved_and_sent", "answered"} <= set(actions_logged)

    client.post("/api/admin/reset")
    assert client.get("/api/summary").json()["queries"] == {"pending_review": DEV_FLAGS}
    assert client.get("/api/audit").json()[0]["action"] == "reset"  # the log itself is never wiped
