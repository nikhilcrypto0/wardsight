"""Export each encounter as a FHIR R4 Bundle, the format Epic exposes.

Diagnoses for the target condition are NOT exported as Condition resources:
in a real hospital stay they live in the doctors' notes (added in the note
step), and finding them there is the detector's job.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path

from wardsight.codes import CHRONIC_ICD10, ICD10, LOINC
from wardsight.models import Encounter, Event
from wardsight.store import admit_ts

NAMESPACE = uuid.UUID("6f1c9a52-6f39-4a8e-9d2b-7e0c1d2a3b4c")
LOINC_SYSTEM = "http://loinc.org"
ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm"
OBS_CATEGORY = "http://terminology.hl7.org/CodeSystem/observation-category"


def _id(*parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


def _ts(enc: Encounter, hours: float) -> str:
    return (admit_ts(enc) + timedelta(hours=hours)).isoformat() + "Z"


def _entry(resource: dict) -> dict:
    return {"fullUrl": f"urn:uuid:{resource['id']}", "resource": resource}


def encounter_bundle(enc: Encounter) -> dict:
    pid = _id("patient", enc.patient.patient_id)
    eid = _id("encounter", enc.encounter_id)
    birth_year = admit_ts(enc).year - enc.patient.age
    resources = [
        {"resourceType": "Patient", "id": pid, "gender": enc.patient.sex,
         "birthDate": f"{birth_year}-01-01",
         "identifier": [{"system": "urn:wardsight:patient", "value": enc.patient.patient_id}]},
        {"resourceType": "Encounter", "id": eid, "status": "finished",
         "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP"},
         "subject": {"reference": f"urn:uuid:{pid}"},
         "identifier": [{"system": "urn:wardsight:encounter", "value": enc.encounter_id}],
         "period": {"start": _ts(enc, 0), "end": _ts(enc, enc.los_days * 24)}},
    ]
    resources += [_problem(pid, flag) for flag in sorted(enc.patient.chronic)]
    resources += [_event_resource(enc, pid, eid, ev, i) for i, ev in enumerate(enc.events)]
    return {"resourceType": "Bundle", "id": _id("bundle", enc.encounter_id),
            "type": "collection", "entry": [_entry(r) for r in resources]}


def _problem(pid: str, flag: str) -> dict:
    code = CHRONIC_ICD10[flag]
    return {"resourceType": "Condition", "id": _id(pid, "problem", flag),
            "category": [{"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                "code": "problem-list-item"}]}],
            "clinicalStatus": {"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                "code": "active"}]},
            "code": {"coding": [{"system": ICD10_SYSTEM, "code": code, "display": ICD10[code]}]},
            "subject": {"reference": f"urn:uuid:{pid}"}}


def _event_resource(enc: Encounter, pid: str, eid: str, ev: Event, i: int) -> dict:
    rid = _id(enc.encounter_id, str(i))
    base = {"id": rid, "subject": {"reference": f"urn:uuid:{pid}"}}
    when = _ts(enc, ev.t_hours)
    if ev.key in LOINC and ev.value is not None:
        code, display, unit = LOINC[ev.key]
        category = "vital-signs" if ev.kind == "vital" else "laboratory"
        return {"resourceType": "Observation", **base, "status": "final",
                "category": [{"coding": [{"system": OBS_CATEGORY, "code": category}]}],
                "code": {"coding": [{"system": LOINC_SYSTEM, "code": code, "display": display}]},
                "encounter": {"reference": f"urn:uuid:{eid}"},
                "effectiveDateTime": when,
                "valueQuantity": {"value": ev.value, "unit": unit,
                                  "system": "http://unitsofmeasure.org", "code": unit}}
    if ev.kind == "med":
        return {"resourceType": "MedicationAdministration", **base, "status": "completed",
                "medicationCodeableConcept": {"text": ev.text},
                "context": {"reference": f"urn:uuid:{eid}"},
                "effectiveDateTime": when}
    if ev.kind == "imaging" or (ev.kind == "lab" and ev.value is None):
        return {"resourceType": "DiagnosticReport", **base, "status": "final",
                "code": {"text": ev.key}, "encounter": {"reference": f"urn:uuid:{eid}"},
                "effectiveDateTime": when, "conclusion": ev.text}
    return {"resourceType": "ServiceRequest", **base, "status": "completed", "intent": "order",
            "code": {"text": ev.text}, "encounter": {"reference": f"urn:uuid:{eid}"},
            "authoredOn": when}


def write_bundles(out_dir: Path, encounters: list[Encounter]) -> int:
    for enc in encounters:
        folder = out_dir / enc.split
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{enc.encounter_id}.json").write_text(json.dumps(encounter_bundle(enc)))
    return len(encounters)
