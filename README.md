# EHR-to-FHIR Cutover

**Legacy patient record migration with clinical-risk validation**

Migrates legacy patient records to FHIR R4 and blocks go-live until every allergy and medication is accounted for.

| | |
|---|---|
| **Migrated** | 1,147 patients · 1,095 allergies · 56,977 medications |
| **Injected errors detected** | 17 / 17, with 0 false positives |
| **Cutover verdict** | BLOCKED → READY after client sign-off |

---

## The story

A fictional veterans' clinic in New York is retiring its aging records system and moving to a FHIR-based EHR. Before the old system is switched off (the **cutover**), someone has to prove that every patient's critical data made it across.

The old system has the problems real legacy systems have: allergies typed in as free text and never coded, medications pointing at patient records that no longer exist, incomplete registrations, and patients registered twice under slightly different names.

## The core idea: not all data errors are equal

A lost allergy record is a patient safety risk. A missing birthdate is a cleanup task. So every check is graded by clinical risk:

| Tier | Data | Rule |
|---|---|---|
| **Critical** | Allergies, medications | Every record must be migrated, or excluded with a documented sign-off. Anything else **blocks go-live** |
| **High** | Patient identity (duplicates) | Must be flagged with evidence for review |
| **Low** | Demographics (e.g., birthdate) | Listed for cleanup; doesn't block |

> **Why block on an uncoded allergy?** FHIR would accept an allergy with only a text description. But the new system needs a code to warn a prescriber. An uncoded "Penicillin" allergy would look fine on screen and never fire an alert.

---

## Results

### First run: BLOCKED

Ten Critical records couldn't migrate: 5 allergies with no code and 5 medications pointing to patients that don't exist. They went to quarantine instead of being silently dropped, and the report blocked go-live.

![BLOCKED cutover report](docs/images/report_blocked.png)

### Client sign-off

The unresolved records went into a **normalization workbook** for the client to review:

- **5 allergies:** suggested codes approved (each suggestion came from other allergies with the same description)
- **4 medications:** relinked to the correct patient
- **1 medication:** excluded, with a documented reason and approver

The pipeline applied these decisions during migration. The legacy data was never changed.

### Second run: READY

All Critical checks pass. Duplicates and cleanup items are still listed, and the exclusion shows who signed off and why.

![READY cutover report](docs/images/report_ready.png)

### Proving the checks work

The pipeline injects 17 known errors into the legacy data and writes an answer key. The validator **never reads the answer key**. A separate scoring step compares its findings afterward:

```
Detected 17 / 17 injected errors

  allergy_missing_code   5 / 5  (check C2)
  orphaned_medication    5 / 5  (check C3)
  missing_birthdate      5 / 5  (check L1)
  duplicate_patient      2 / 2  (check H1)

Flagged but not injected: 0
```

---

## Architecture

```mermaid
flowchart LR
    A[Synthea<br/>synthetic patients] -->|CSV| B[(Legacy DB<br/>PostgreSQL)]
    B -->|inject 17 known errors| B
    B --> C[migrate.py]
    C -->|FHIR R4, batch PUT| D[(HAPI FHIR<br/>server)]
    C -->|can't migrate| E[(Quarantine<br/>+ reason)]
    E --> F[Normalization<br/>workbook]
    F -->|client decisions| C
    B --> G[validate.py]
    D --> G
    E --> G
    G --> H{Go / No-Go<br/>report}
```

## How it works

**1. Legacy system.** [Synthea](https://github.com/synthetichealth/synthea) generates patients, allergies and medications, loaded into a deliberately old-fashioned PostgreSQL schema: nullable columns, text IDs, no foreign keys. A seeded script then injects 17 errors and records each one in an answer key.

**2. Mapping spec.** Every legacy column is mapped to a FHIR field with a conversion rule, and the spec defines the acceptance tests. Full spec: [`docs/mapping_spec.md`](docs/mapping_spec.md).

**3. Migration.** Records are converted to FHIR `Patient`, `AllergyIntolerance` and `MedicationRequest` resources and loaded into HAPI FHIR in batch bundles of 500, using `PUT` with legacy-based IDs, so reruns update instead of duplicating. Anything that can't migrate goes to a quarantine table with a reason. **Nothing is silently dropped.**

**4. Validation.** The validator doesn't trust the migration's own numbers. It reads everything back from HAPI and recounts. It also separates records **quarantined on purpose** from records **missing with no quarantine record**, which would mean silent data loss.

**5. Go/No-Go report.** Any Critical failure means **BLOCKED**. Otherwise the cutover is **READY**.

### The checks

| ID | Tier | Check |
|---|---|---|
| C1–C3 | Critical | Patients, allergies, medications reconciled: in FHIR or excluded with sign-off |
| C4 | Critical | Every migrated allergy and medication has a code |
| C5 | Critical | Every allergy and medication links to a patient that exists |
| C6 | Critical | Value counts match the source (gender, active/resolved, active/completed) |
| C7 | Critical | 20 random records match the source field by field |
| H1 | High | Possible duplicate patients (same birthdate + SSN), shown with both names |
| L1 | Low | Patients missing a birthdate |
| L2 | Low | Allergies with no named allergen ("Allergic disposition") |

---

## A problem found along the way

The first migration run crashed: **every allergy Synthea generated had its code system recorded as `Unknown`**, a value the mapping spec didn't cover.

Quarantining 1,090 allergies would have blocked the cutover for no good reason, and assuming "Unknown means SNOMED" would have mislabeled the drug allergies. Instead, I built a **reviewed crosswalk** of the 22 distinct codes, each assigned from evidence in the data:

- **16 SNOMED:** each description ends in a SNOMED semantic tag, such as `Peanut (substance)` or `Mold (organism)`
- **6 RxNorm:** no semantic tag, and each code is the RxNorm ingredient code for the named drug, such as `1191` for aspirin

Any code that can't be confirmed still goes to quarantine. The full evidence table is in [`docs/mapping_spec.md`](docs/mapping_spec.md#code-system-crosswalk).

## Mapping summary

| Legacy | FHIR R4 | Rule |
|---|---|---|
| `patients` | `Patient` | Gender `M`/`F` → `male`/`female`; missing birthdate left out and flagged (Low) |
| `allergies` | `AllergyIntolerance` | Missing code or missing patient → quarantine; `Unknown` code system → crosswalk |
| `medications` | `MedicationRequest` | Missing patient → quarantine; no stop date → `active`, else `completed` |
| `encounter_id` | — | Not migrated (out of scope), documented rather than silently dropped |

---

## Setup

**Prerequisites:** [Docker](https://www.docker.com/), [uv](https://docs.astral.sh/uv/), Java 17+, [GitHub CLI](https://cli.github.com/)

```bash
# 1. Clone and install (Python 3.14, pinned)
gh repo clone vtorreno/ehr-to-fhir-cutover
cd ehr-to-fhir-cutover
uv sync
cp .env.example .env    # then fill in DATABASE_URL (see below)

# 2. Start PostgreSQL 18 and HAPI FHIR
docker run --name legacy-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=clinic_legacy \
  -p 5432:5432 -v legacy-data:/var/lib/postgresql --restart unless-stopped -d postgres:18
docker run --name fhir-server -p 8080:8080 --restart unless-stopped -d hapiproject/hapi:latest

# 3. Generate the data (Synthea v4.0.0, seed 11, New York)
mkdir -p tools data/raw
gh release download v4.0.0 --repo synthetichealth/synthea \
  --pattern 'synthea-with-dependencies.jar' --dir tools
mv tools/synthea-with-dependencies.jar tools/synthea.jar
java -jar tools/synthea.jar -p 1000 -s 11 -cs 11 -r 20261110 \
  --exporter.csv.export=true --exporter.fhir.export=false "New York"
cp output/csv/{patients,allergies,medications}.csv data/raw/
```

The same seed, reference date and Synthea version always produce the same patients, so your counts should match the ones above.

### Environment variables

`.env.example` lists the settings the scripts need. Copy it to `.env` (which is gitignored) and fill it in:

```
DATABASE_URL=
FHIR_URL=http://localhost:8080/fhir
```

| Variable | What it is | Value for the Docker setup above |
|---|---|---|
| `DATABASE_URL` | Connection string for the legacy PostgreSQL database | `postgresql://postgres:postgres@localhost:5432/clinic_legacy` |
| `FHIR_URL` | Base URL of the HAPI FHIR server | `http://localhost:8080/fhir` (already filled in) |

Every script is run with `uv run --env-file .env ...`, which loads these values.

## Running the pipeline

```bash
# Build the legacy system
docker exec -i legacy-db psql -U postgres -d clinic_legacy < sql/01_legacy_schema.sql
uv run --env-file .env scripts/load_legacy.py
uv run --env-file .env scripts/inject_errors.py

# Migrate, validate, report  ->  BLOCKED
docker exec -i legacy-db psql -U postgres -d clinic_legacy < sql/04_quarantine.sql
uv run --env-file .env scripts/migrate.py
uv run --env-file .env scripts/validate.py
uv run --env-file .env scripts/report.py
uv run --env-file .env scripts/score.py          # 17 / 17

# Client sign-off  ->  READY
uv run --env-file .env scripts/make_workbook.py  # then fill in the workbook
uv run --env-file .env scripts/apply_workbook.py
uv run --env-file .env scripts/migrate.py
uv run --env-file .env scripts/validate.py
uv run --env-file .env scripts/report.py
```

## Project structure

```
ehr-to-fhir-cutover/
├── sql/
│   ├── 01_legacy_schema.sql       # legacy tables (no foreign keys, on purpose)
│   └── 04_quarantine.sql          # quarantine table
├── scripts/
│   ├── db.py                      # database connections
│   ├── codes.py                   # code systems + reviewed crosswalk
│   ├── load_legacy.py             # Synthea CSV → legacy tables
│   ├── inject_errors.py           # 17 known errors + answer key
│   ├── migrate.py                 # legacy → FHIR, with quarantine
│   ├── make_workbook.py           # quarantine → normalization workbook
│   ├── apply_workbook.py          # client decisions → migration.decisions
│   ├── validate.py                # tiered checks, read from HAPI
│   ├── score.py                   # findings vs. answer key
│   └── report.py                  # Go/No-Go report
├── data/injected_errors.json      # answer key (validation never reads it)
├── docs/
│   ├── mapping_spec.md            # mapping rules, crosswalk, acceptance tests
│   └── images/                    # report screenshots
├── normalization/                 # completed workbook (client sign-off)
├── reports/                       # BLOCKED and READY reports + validation results
└── .env.example                   # settings template (copy to .env)
```

## Tech stack

Python 3.14 (uv) · PostgreSQL 18 · HAPI FHIR · FHIR R4 · Docker · pandas · SQLAlchemy · Psycopg 3 · openpyxl · Synthea

All data is synthetic. No real patient information is used anywhere.