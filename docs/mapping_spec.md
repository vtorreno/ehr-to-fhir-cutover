# Mapping Spec: Legacy Clinic Database → FHIR R4

**Source:** `legacy` schema in PostgreSQL (`patients`, `allergies`, `medications`)
**Target:** HAPI FHIR server, FHIR R4 (`Patient`, `AllergyIntolerance`, `MedicationRequest`)
**Status:** Draft. Confirm the items under [To confirm from the profile](#to-confirm-from-the-profile) against `docs/data_profile.txt`.

---

## Risk tiers

| Tier | Data | Rule for cutover |
|---|---|---|
| **Critical** | Allergies, medications | Every record must be migrated, or excluded with a documented sign-off. Anything else **blocks** go-live |
| **High** | Patient identity (duplicates) | Must be flagged and explained |
| **Low** | Demographics (e.g., birthdate) | Flagged for cleanup; doesn't block |

---

## Patient

| Legacy column | FHIR field | Rule |
|---|---|---|
| patient_id | `id` | Copy as-is |
| first_name | `name.given` | Copy as-is |
| last_name | `name.family` | Copy as-is |
| birth_date | `birthDate` | If missing: leave out, flag for cleanup (Low) |
| death_date | `deceasedDateTime` | If missing: leave out |
| gender | `gender` | `M` → `male`, `F` → `female`, anything else → `unknown` |
| ssn | `identifier` (system `http://hl7.org/fhir/sid/us-ssn`) | Copy as-is (synthetic data) |
| address, city, state, zip | `address.line`, `address.city`, `address.state`, `address.postalCode` | Copy as-is |

**Duplicates (High):** patients who share a birthdate and SSN are both migrated, not merged. The cutover report lists each pair with the evidence (e.g., `Garcia` / `Gracia`) for a person to review.

**Deceased patients** are migrated like any other patient.

---

## AllergyIntolerance (Critical)

| Legacy column | FHIR field | Rule |
|---|---|---|
| allergy_id | `id` | `legacy-allergy-{allergy_id}` |
| patient_id | `patient` | `Patient/{patient_id}`. If the patient doesn't exist: **quarantine** (`PATIENT_NOT_FOUND`) |
| code + code_system | `code.coding` | System URI per the rules below. If the code is missing: **quarantine** (`ALLERGY_CODE_MISSING`) |
| description | `code.text` | Copy as-is |
| start_date | `onsetDateTime` | Copy as-is |
| stop_date | `clinicalStatus` | Empty → `active`; set → `resolved` |
| allergy_type | `type` | Lowercase (`allergy` / `intolerance`) |
| category | `category` | Lowercase (`food` / `medication` / `environment`) |
| reaction_code + reaction_desc | `reaction.manifestation` | Only if a reaction exists (FHIR requires a manifestation in every reaction) |
| severity | `reaction.severity` | Lowercase (`mild` / `moderate` / `severe`) |
| encounter_id | — | Not migrated: encounters are out of scope |

**Why an uncoded allergy is quarantined instead of loaded as text:** FHIR accepts an allergy with only a text description. But the new system needs a code to warn a prescriber about a drug allergy. An uncoded "Penicillin" allergy would look fine on screen and never fire an alert.

---

## MedicationRequest (Critical)

| Legacy column | FHIR field | Rule |
|---|---|---|
| medication_id | `id` | `legacy-med-{medication_id}` |
| patient_id | `subject` | `Patient/{patient_id}`. If the patient doesn't exist: **quarantine** (`PATIENT_NOT_FOUND`) |
| rxnorm_code + description | `medicationCodeableConcept.coding` | RxNorm system; description as display |
| start_ts | `authoredOn` | Copy as-is (with time zone) |
| stop_ts | `status` | Empty → `active`; set → `completed` |
| reason_code + reason_desc | `reasonCode` | Leave out if empty |
| *(none)* | `intent` | Always `order` (required by FHIR) |
| encounter_id | — | Not migrated: encounters are out of scope |

---

## Rules for every resource

- **IDs come from legacy keys,** loaded with `PUT`, so rerunning the migration updates records instead of creating copies.
- **Empty values are left out** of the FHIR resource, never sent as empty strings.
- **Code systems:**
  - `SNOMED-CT` → `http://snomed.info/sct`
  - `RxNorm` → `http://www.nlm.nih.gov/research/umls/rxnorm`
- **Nothing is silently dropped.** Every source record is either loaded or quarantined with a reason. Columns that aren't migrated (`encounter_id`) are listed above.

---

## Quarantine

Records that can't be migrated are written to a quarantine table with a reason.

| Reason | Meaning | Resolution |
|---|---|---|
| `ALLERGY_CODE_MISSING` | Allergy has a description but no code | Client confirms a code in the normalization workbook |
| `PATIENT_NOT_FOUND` | Record points to a patient that doesn't exist | Client relinks it to the right patient, or excludes it with a reason, in the workbook |
| `FHIR_REJECTED` | The FHIR server refused the record | Read the server's error, fix the conversion, rerun |

Missing birthdates and duplicate patients are **not** quarantined. They migrate and are flagged in the cutover report.

---

## Normalization workbook

The pipeline generates an Excel workbook from the quarantine table. The client fills in a decision for each row, and the pipeline reads it back.

**Allergy codes sheet**

| allergy_id | description | suggested_code | decision | final_code | reviewed_by |
|---|---|---|---|---|---|

- `suggested_code` comes from other allergies in the source data with the same description.
- `decision`: `APPROVE` (use the suggested code) or `CHANGE` (use `final_code`).

**Orphaned medications sheet**

| medication_id | description | decision | correct_patient_id | reason | approved_by |
|---|---|---|---|---|---|

- `decision`: `RELINK` (to `correct_patient_id`, which must exist) or `EXCLUDE` (requires `reason` and `approved_by`).

**When read back:**
- A blank decision keeps the record in quarantine, and the cutover stays **BLOCKED**.
- An excluded record counts as accounted for, because it has a documented sign-off.
- An invalid row is reported as an error, never skipped.

---

## Acceptance tests

| # | Test | Pass condition |
|---|---|---|
| 1 | Counts | For each table: source rows = loaded + quarantined |
| 2 | Links | Every loaded allergy and medication references a patient that exists in FHIR |
| 3 | Codes | 100% of loaded allergies and medications have a code |
| 4 | Values | Counts per value match the source (gender, active/resolved, active/completed) |
| 5 | Spot check | 20 random records match the source field by field |
| 6 | Quarantine | First run: exactly 10 records (5 `ALLERGY_CODE_MISSING`, 5 `PATIENT_NOT_FOUND`) |

**Go/No-Go:** the cutover is **READY** only when tests 1–5 pass and no Critical record is left unresolved in quarantine.

---

## To confirm from the profile

- [ ] Code system values are exactly `SNOMED-CT` and `RxNorm`
- [ ] Gender values are only `M` and `F`
- [ ] Severity values are only `MILD`, `MODERATE`, `SEVERE` (or empty)
- [ ] Allergy types and categories match the values listed above
- [ ] No medications are missing an RxNorm code
- [ ] Each of the 5 uncoded allergy descriptions also appears elsewhere with a code