CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS patients (
    id          TEXT PRIMARY KEY,
    birth_date  DATE,
    sex         TEXT,
    summary     JSONB NOT NULL          -- conditions, latest labs, medications
);

CREATE TABLE IF NOT EXISTS trials (
    nct_id         TEXT PRIMARY KEY,
    title          TEXT,
    conditions     TEXT[],
    phases         TEXT[],
    criteria_text  TEXT,
    raw            JSONB NOT NULL,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per parsed eligibility criterion; source_text keeps every decision explainable
CREATE TABLE IF NOT EXISTS trial_constraints (
    id           SERIAL PRIMARY KEY,
    nct_id       TEXT NOT NULL REFERENCES trials(nct_id) ON DELETE CASCADE,
    kind         TEXT NOT NULL CHECK (kind IN ('inclusion', 'exclusion')),
    field        TEXT NOT NULL,
    operator     TEXT NOT NULL,
    value        TEXT,
    unit         TEXT,
    evaluable    BOOLEAN NOT NULL,
    source_text  TEXT NOT NULL,
    parsed_by    TEXT NOT NULL,
    parsed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_constraints_nct ON trial_constraints(nct_id);
