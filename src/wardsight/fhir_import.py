"""Read FHIR R4 data (the format Epic exposes) into a Chart the engine can review.

Two sources:
- a FHIR Bundle file, e.g. one written by `fhir_export`
- a live FHIR R4 server, e.g. the public SMART Health IT sandbox (synthetic data,
  no login): https://r4.smarthealthit.org

    uv run wardsight-fhir --bundle data/fhir/dev/D0011.json
    uv run wardsight-fhir --server https://r4.smarthealthit.org --patient <id>

Only the evidence rules run on imported data: a server patient has no admission
reason or note text in WardSight's format, so DRG grouping and the note reader
are skipped and the report says so.
"""

from __future__ import annotations

import argparse
import json
import logging
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from wardsight.codes import LOINC
from wardsight.engine.chart import Chart
from wardsight.engine.evidence import RULES
from wardsight.models import Event

log = logging.getLogger("wardsight.fhir")

LOINC_TO_KEY = {code: key for key, (code, _, _) in LOINC.items()}
VITAL_KEYS = {"heart_rate", "resp_rate", "sbp", "dbp", "map", "spo2", "temp", "o2_flow"}
USER_AGENT = "wardsight-fhir-import/0.1"
SERVER_PAGE_SIZE = 200
MAX_PAGES = 10


def _when(value: str | None) -> datetime | None:
    """Parse a FHIR dateTime to naive UTC, so times with different offsets line up."""
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed


def _hours(start: datetime, when: datetime | None) -> float | None:
    return None if when is None else round((when - start).total_seconds() / 3600, 3)


def _loinc_key(resource: dict) -> str | None:
    for coding in resource.get("code", {}).get("coding", []):
        if coding.get("system") == "http://loinc.org" and coding.get("code") in LOINC_TO_KEY:
            return LOINC_TO_KEY[coding["code"]]
    return None


def resources_to_chart(resources: list[dict], encounter_id: str = "FHIR") -> Chart:
    """Build a Chart from FHIR resources (Patient, Encounter, Observation, ...)."""
    by_type: dict[str, list[dict]] = {}
    for r in resources:
        by_type.setdefault(r.get("resourceType", ""), []).append(r)
    patient = (by_type.get("Patient") or [{}])[0]
    encounters = by_type.get("Encounter") or []
    period = (encounters[0].get("period", {}) if encounters else {})
    times = [_when(o.get("effectiveDateTime")) for o in by_type.get("Observation", [])]
    start = _when(period.get("start")) or min((t for t in times if t), default=datetime(2000, 1, 1))
    end = _when(period.get("end")) or max((t for t in times if t), default=start)
    birth = patient.get("birthDate")
    age = start.year - int(birth[:4]) if birth else 0

    events: list[Event] = []
    for obs in by_type.get("Observation", []):
        key, quantity = _loinc_key(obs), obs.get("valueQuantity", {})
        hour = _hours(start, _when(obs.get("effectiveDateTime")))
        if key and hour is not None and "value" in quantity:
            events.append(Event(hour, "vital" if key in VITAL_KEYS else "lab", key, float(quantity["value"])))
    for rtype, kind, text_of, time_field in (
            ("MedicationAdministration", "med", lambda r: r.get("medicationCodeableConcept", {}).get("text"),
             "effectiveDateTime"),
            ("ServiceRequest", "order", lambda r: r.get("code", {}).get("text"), "authoredOn"),
            ("DiagnosticReport", "imaging", lambda r: r.get("conclusion"), "effectiveDateTime")):
        for r in by_type.get(rtype, []):
            hour, text = _hours(start, _when(r.get(time_field))), text_of(r)
            if hour is not None and text:
                events.append(Event(hour, kind, rtype.lower(), None, text))

    problems = tuple(sorted({c["code"] for cond in by_type.get("Condition", [])
                             for c in cond.get("code", {}).get("coding", [])
                             if c.get("system") == "http://hl7.org/fhir/sid/icd-10-cm"}))
    los_days = max(1, round((end - start).total_seconds() / 86400))
    return Chart(encounter_id, "fhir", age, patient.get("gender", "unknown"), los_days, "",
                 problems, tuple(sorted(events, key=lambda e: (e.t_hours, e.kind, e.key))), ())


def bundle_to_chart(bundle: dict, encounter_id: str = "FHIR") -> Chart:
    return resources_to_chart([e["resource"] for e in bundle.get("entry", [])], encounter_id)


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/fhir+json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_patient(server: str, patient_id: str) -> list[dict]:
    """Patient plus their Observations from an open FHIR R4 server (follows paging)."""
    base = server.rstrip("/")
    resources = [_get(f"{base}/Patient/{urllib.parse.quote(patient_id)}")]
    url: str | None = f"{base}/Observation?patient={urllib.parse.quote(patient_id)}&_count={SERVER_PAGE_SIZE}"
    for _ in range(MAX_PAGES):
        if not url:
            break
        page = _get(url)
        resources += [e["resource"] for e in page.get("entry", [])]
        url = next((link["url"] for link in page.get("link", []) if link.get("relation") == "next"), None)
    return resources


def evidence_report(chart: Chart) -> dict:
    measured = sorted({e.key for e in chart.events if e.value is not None})
    results = {}
    for condition, rule in RULES.items():
        ev = rule(chart)
        results[condition] = {"met": ev.met, "evidence": ev.summary()}
    return {"patient_age": chart.age, "sex": chart.sex, "events": len(chart.events),
            "measured": measured, "rules": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run WardSight's evidence rules on FHIR R4 data.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bundle", type=Path, help="a FHIR Bundle JSON file")
    source.add_argument("--server", help="an open FHIR R4 base URL")
    parser.add_argument("--patient", help="patient id on the server")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.bundle:
        chart = bundle_to_chart(json.loads(args.bundle.read_text()), args.bundle.stem)
    else:
        if not args.patient:
            parser.error("--server needs --patient")
        chart = resources_to_chart(fetch_patient(args.server, args.patient), args.patient)
    log.info(json.dumps(evidence_report(chart), indent=2))
    log.info("Note: DRG grouping and the note reader need WardSight's admission reason and notes; "
             "only the evidence rules ran.")


if __name__ == "__main__":
    main()
