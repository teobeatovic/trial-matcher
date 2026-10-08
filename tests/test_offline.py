"""Offline tests: no network, no database, no API key needed."""
from datetime import date

from app.ingest.patients import summarize_bundle
from app.ingest.trials import to_row
from app.parse.criteria import split_sections, validate

CRITERIA = """Inclusion Criteria:

* Age >= 18 years
* ECOG performance status 0-1

Exclusion Criteria:

* Prior anti-PD-1 therapy
"""


def test_split_sections():
    s = split_sections(CRITERIA)
    assert "Age >= 18 years" in s["inclusion"]
    assert "anti-PD-1" in s["exclusion"]
    assert "anti-PD-1" not in s["inclusion"]


def test_validate_drops_hallucinated_source_text():
    good = {"field": "age", "operator": "gte", "value": "18", "unit": "years",
            "evaluable": True, "source_text": "Age >= 18 years"}
    fake = {**good, "source_text": "Age >= 21 years"}
    bad_field = {**good, "field": "shoe_size"}
    assert validate([good, fake, bad_field], CRITERIA) == [good]


def test_to_row():
    study = {"protocolSection": {
        "identificationModule": {"nctId": "NCT00000001", "briefTitle": "A trial"},
        "conditionsModule": {"conditions": ["Breast Cancer"]},
        "designModule": {"phases": ["PHASE2"]},
        "eligibilityModule": {"eligibilityCriteria": CRITERIA},
    }}
    row = to_row(study)
    assert row["nct_id"] == "NCT00000001" and row["phases"] == ["PHASE2"]


def test_summarize_bundle_keeps_latest_lab():
    bundle = {"entry": [
        {"resource": {"resourceType": "Patient", "id": "p1",
                      "birthDate": "1970-06-15", "gender": "female"}},
        {"resource": {"resourceType": "Condition",
                      "code": {"coding": [{"display": "Malignant neoplasm of breast"}]},
                      "clinicalStatus": {"coding": [{"code": "active"}]},
                      "onsetDateTime": "2024-01-10"}},
        {"resource": {"resourceType": "Observation",
                      "code": {"coding": [{"display": "Hemoglobin"}]},
                      "effectiveDateTime": "2023-01-01",
                      "valueQuantity": {"value": 11.0, "unit": "g/dL"}}},
        {"resource": {"resourceType": "Observation",
                      "code": {"coding": [{"display": "Hemoglobin"}]},
                      "effectiveDateTime": "2025-01-01",
                      "valueQuantity": {"value": 13.2, "unit": "g/dL"}}},
    ]}
    row = summarize_bundle(bundle, today=date(2026, 10, 7))
    assert row["summary"]["age"] == 56
    assert row["summary"]["latest_labs"]["Hemoglobin"]["value"] == 13.2
    assert "Malignant neoplasm of breast" in row["summary"]["conditions"]
