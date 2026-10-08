# Clinical Trial Matching Agent

Matches synthetic patients to recruiting oncology trials and explains every
pass/fail decision, criterion by criterion.

> Research demo only. Not for clinical use. Uses only synthetic patients (Synthea)
> and public trial data (ClinicalTrials.gov). No real patient data.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # add your Cohere API key
docker compose up -d              # Postgres + pgvector, schema auto-applied
pytest -q                         # offline tests, no key or DB needed
```

## Step 1: synthetic patients

```bash
# Needs Java 17+
curl -L -o synthea.jar https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar
java -jar synthea.jar -p 50 -m breast_cancer --exporter.baseDirectory=./data/synthea
python -m app.ingest.patients data/synthea/fhir
```

Check `java -jar synthea.jar -h` and the Synthea wiki if the module name differs.
Patients that never develop the condition are normal; generate more if needed.

## Step 2: recruiting trials

```bash
python -m app.ingest.trials "breast cancer" --limit 100
```

## Step 3: parse eligibility criteria

```bash
python -m app.parse.criteria --limit 20
```

Inclusion/exclusion sections are split deterministically, then a Cohere model
turns each into structured constraints. Any constraint whose `source_text` is
not found verbatim in the original criteria is dropped as hallucinated.

## Roadmap

- [x] Ingest synthetic patients (FHIR -> compact summary)
- [x] Ingest recruiting trials (ClinicalTrials.gov v2 API)
- [x] LLM criteria parser with schema + verbatim-source validation
- [ ] Hand-label ~30 trials -> measure parser precision/recall (`eval/`)
- [ ] Deterministic matcher: each constraint -> pass / fail / unknown + reason
- [ ] Agent with tools: `get_patient`, `search_trials`, `evaluate_criteria`
- [ ] De-identification layer before any LLM call (CPU-only, from scratch)
- [ ] FastAPI backend + React/TypeScript UI
- [ ] Docker + Kubernetes deploy (kind or k3s)
