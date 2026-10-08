"""Fetch recruiting trials from the ClinicalTrials.gov v2 API and store them.

Usage: python -m app.ingest.trials "breast cancer" --limit 100
"""
import argparse
import time

import requests
from psycopg2.extras import Json

from app.db import get_conn

API_URL = "https://clinicaltrials.gov/api/v2/studies"


def fetch_trials(condition: str, limit: int = 100) -> list[dict]:
    """Page through recruiting studies for a condition, up to `limit`."""
    studies, token = [], None
    while len(studies) < limit:
        params = {
            "query.cond": condition,
            "filter.overallStatus": "RECRUITING",
            "pageSize": min(100, limit - len(studies)),
        }
        if token:
            params["pageToken"] = token
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        studies.extend(body.get("studies", []))
        token = body.get("nextPageToken")
        if not token:
            break
        time.sleep(0.5)  # be polite to a public API
    return studies[:limit]


def to_row(study: dict) -> dict:
    ps = study.get("protocolSection", {})
    return {
        "nct_id": ps.get("identificationModule", {}).get("nctId"),
        "title": ps.get("identificationModule", {}).get("briefTitle"),
        "conditions": ps.get("conditionsModule", {}).get("conditions", []),
        "phases": ps.get("designModule", {}).get("phases", []),
        "criteria_text": ps.get("eligibilityModule", {}).get("eligibilityCriteria", ""),
        "raw": ps,
    }


def save_trials(rows: list[dict]) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO trials (nct_id, title, conditions, phases, criteria_text, raw)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (nct_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    conditions = EXCLUDED.conditions,
                    phases = EXCLUDED.phases,
                    criteria_text = EXCLUDED.criteria_text,
                    raw = EXCLUDED.raw,
                    fetched_at = now()
                """,
                (r["nct_id"], r["title"], r["conditions"], r["phases"],
                 r["criteria_text"], Json(r["raw"])),
            )
    return len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("condition")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    rows = [to_row(s) for s in fetch_trials(args.condition, args.limit)]
    rows = [r for r in rows if r["nct_id"] and r["criteria_text"]]
    print(f"Saved {save_trials(rows)} trials for '{args.condition}'")
