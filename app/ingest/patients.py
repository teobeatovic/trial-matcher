"""Load Synthea FHIR R4 bundles into a compact patient summary.

Usage: python -m app.ingest.patients data/synthea/fhir
"""
import argparse
import json
from datetime import date
from pathlib import Path

from psycopg2.extras import Json

from app.db import get_conn


def _display(concept: dict | None) -> str | None:
    if not concept:
        return None
    codings = concept.get("coding") or []
    return concept.get("text") or (codings[0].get("display") if codings else None)


def _age(birth: str | None, today: date | None = None) -> int | None:
    if not birth:
        return None
    b = date.fromisoformat(birth[:10])
    t = today or date.today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def summarize_bundle(bundle: dict, today: date | None = None) -> dict:
    """Reduce a FHIR bundle to what eligibility checks actually need."""
    patient, conditions, labs, meds = None, {}, {}, set()

    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        rtype = res.get("resourceType")

        if rtype == "Patient":
            patient = res

        elif rtype == "Condition":
            name = _display(res.get("code"))
            status = _display(res.get("clinicalStatus")) or "unknown"
            if name:
                conditions[name] = {
                    "status": status,
                    "onset": res.get("onsetDateTime"),
                }

        elif rtype == "Observation" and "valueQuantity" in res:
            name = _display(res.get("code"))
            when = res.get("effectiveDateTime") or ""
            if name and when >= labs.get(name, {}).get("date", ""):
                vq = res["valueQuantity"]
                labs[name] = {"value": vq.get("value"), "unit": vq.get("unit"), "date": when}

        elif rtype == "MedicationRequest":
            name = _display(res.get("medicationCodeableConcept"))
            if name:
                meds.add(name)

    if patient is None:
        raise ValueError("Bundle has no Patient resource")

    birth = patient.get("birthDate")
    return {
        "id": patient["id"],
        "birth_date": birth,
        "sex": patient.get("gender"),
        "summary": {
            "age": _age(birth, today),
            "sex": patient.get("gender"),
            "conditions": conditions,
            "latest_labs": labs,
            "medications": sorted(meds),
        },
    }


def save_patients(rows: list[dict]) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO patients (id, birth_date, sex, summary)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET summary = EXCLUDED.summary
                """,
                (r["id"], r["birth_date"], r["sex"], Json(r["summary"])),
            )
    return len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("fhir_dir")
    args = ap.parse_args()
    rows = []
    for path in Path(args.fhir_dir).glob("*.json"):
        bundle = json.loads(path.read_text())
        if any(e.get("resource", {}).get("resourceType") == "Patient"
               for e in bundle.get("entry", [])):
            rows.append(summarize_bundle(bundle))
    print(f"Saved {save_patients(rows)} patients")
