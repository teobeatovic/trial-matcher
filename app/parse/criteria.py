"""Parse free-text eligibility criteria into structured constraints with Cohere.

Usage: python -m app.parse.criteria --limit 20
"""
import argparse
import json
import os
import re

import cohere

from app.db import get_conn

FIELDS = ["age", "sex", "diagnosis", "stage", "biomarker", "lab_value",
          "performance_status", "prior_therapy", "medication", "comorbidity", "other"]
OPERATORS = ["eq", "ne", "gt", "gte", "lt", "lte", "present", "absent"]

SCHEMA = {
    "type": "object",
    "required": ["constraints"],
    "properties": {
        "constraints": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["field", "operator", "value", "unit", "evaluable", "source_text"],
                "properties": {
                    "field": {"type": "string", "enum": FIELDS},
                    "operator": {"type": "string", "enum": OPERATORS},
                    "value": {"type": "string"},
                    "unit": {"type": "string"},
                    "evaluable": {"type": "boolean"},
                    "source_text": {"type": "string"},
                },
            },
        }
    },
}

PROMPT = """Generate a JSON object listing the eligibility constraints in this {kind} criteria section of a clinical trial.

Rules:
- One constraint per atomic requirement. Split compound bullets.
- source_text must be copied verbatim from the criteria.
- value is a string ("18", "female", "HER2-positive", "1500"); use "" when not applicable.
- unit is "" when not applicable.
- evaluable is true only if the requirement could be checked from structured EHR data
  (age, sex, diagnoses, lab values, medications). Subjective or consent-type criteria are false.
- For ECOG ranges like "ECOG 0-1", use field performance_status, operator lte, value "1".

Criteria:
{text}"""

_HEADER = re.compile(r"^\s*(inclusion|exclusion)\s+criteria\s*:?\s*$", re.I | re.M)


def split_sections(criteria_text: str) -> dict[str, str]:
    """Split raw criteria into inclusion/exclusion sections deterministically."""
    matches = list(_HEADER.finditer(criteria_text))
    if not matches:
        return {"inclusion": criteria_text.strip()}
    sections = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(criteria_text)
        kind = m.group(1).lower()
        body = criteria_text[m.end():end].strip()
        if body:
            sections[kind] = (sections.get(kind, "") + "\n" + body).strip()
    return sections


def validate(constraints: list[dict], source: str) -> list[dict]:
    """Drop anything malformed or hallucinated (source_text not found in the criteria)."""
    norm = " ".join(source.split()).lower()
    kept = []
    for c in constraints:
        if c.get("field") not in FIELDS or c.get("operator") not in OPERATORS:
            continue
        if " ".join(c.get("source_text", "").split()).lower() not in norm:
            continue
        kept.append(c)
    return kept


def parse_section(co: cohere.ClientV2, model: str, kind: str, text: str) -> list[dict]:
    resp = co.chat(
        model=model,
        messages=[{"role": "user", "content": PROMPT.format(kind=kind, text=text)}],
        response_format={"type": "json_object", "json_schema": SCHEMA},
        temperature=0,
    )
    data = json.loads(resp.message.content[0].text)
    return validate(data.get("constraints", []), text)


def run(limit: int) -> None:
    co = cohere.ClientV2()  # reads CO_API_KEY
    model = os.environ.get("COHERE_MODEL", "command-a-03-2025")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT nct_id, criteria_text FROM trials t
            WHERE NOT EXISTS (SELECT 1 FROM trial_constraints c WHERE c.nct_id = t.nct_id)
            LIMIT %s
            """,
            (limit,),
        )
        for nct_id, text in cur.fetchall():
            total = 0
            for kind, section in split_sections(text).items():
                for c in parse_section(co, model, kind, section):
                    cur.execute(
                        """
                        INSERT INTO trial_constraints
                            (nct_id, kind, field, operator, value, unit, evaluable, source_text, parsed_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (nct_id, kind, c["field"], c["operator"], c["value"] or None,
                         c["unit"] or None, c["evaluable"], c["source_text"], model),
                    )
                    total += 1
            conn.commit()
            print(f"{nct_id}: {total} constraints")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    run(ap.parse_args().limit)
