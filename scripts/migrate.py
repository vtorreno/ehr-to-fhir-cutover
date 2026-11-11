"""
Migrate the legacy data to FHIR, quarantining anything that can't migrate.
"""

import os
import requests
from psycopg.rows import dict_row
from codes import RXNORM, SNOMED, code_system
from db import get_connection

FHIR_URL = os.environ["FHIR_URL"]
BATCH_SIZE = 500

GENDERS = {"M": "male", "F": "female"}

# --- Helpers -----------------------------------------------------------------

def iso(value):
    """Date or timestamp -> ISO 8601 string (None stays None)."""
    return value.isoformat() if value else None

def lower(value):
    return value.lower() if value else None

def clean(obj):
    """Remove empty values. FHIR rejects nulls and empty strings."""
    if isinstance(obj, dict):
        obj = {k: clean(v) for k, v in obj.items()}
        return {k: v for k, v in obj.items() if v not in (None, "", [], {})}
    if isinstance(obj, list):
        obj = [clean(v) for v in obj]
        return [v for v in obj if v not in (None, "", [], {})]
    return obj

def concept(system, code, text):
    return {"coding": [{"system": system, "code": code, "display": text}], "text": text}

# --- Legacy row -> FHIR resource ----------------------------------------------

def to_patient(r):
    return clean({
        "resourceType": "Patient",
        "id": r["patient_id"],
        "identifier": [{"system": "http://hl7.org/fhir/sid/us-ssn", "value": r["ssn"]}],
        "name": [{"use": "official", "family": r["last_name"], "given": [r["first_name"]]}],
        "gender": GENDERS.get(r["gender"], "unknown"),
        "birthDate": iso(r["birth_date"]),
        "deceasedDateTime": iso(r["death_date"]),
        "address": [{"line": [r["address"]], "city": r["city"],
                     "state": r["state"], "postalCode": r["zip"]}],
    })

def to_allergy(r):
    reaction = None
    if r["reaction_code"]:
        reaction = [{"manifestation": [concept(SNOMED, r["reaction_code"], r["reaction_desc"])],
                     "severity": lower(r["severity"])}]
    return clean({
        "resourceType": "AllergyIntolerance",
        "id": f"legacy-allergy-{r['allergy_id']}",
        "clinicalStatus": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
            "code": "resolved" if r["stop_date"] else "active"}]},
        "type": lower(r["allergy_type"]),
        "category": [lower(r["category"])],
        "code": concept(code_system(r["code_system"], r["code"]), r["code"], r["description"]),
        "patient": {"reference": f"Patient/{r['patient_id']}"},
        "onsetDateTime": iso(r["start_date"]),
        "reaction": reaction,
    })

def to_medication(r):
    reason = [concept(SNOMED, r["reason_code"], r["reason_desc"])] if r["reason_code"] else None
    return clean({
        "resourceType": "MedicationRequest",
        "id": f"legacy-med-{r['medication_id']}",
        "status": "completed" if r["stop_ts"] else "active",
        "intent": "order",
        "medicationCodeableConcept": concept(RXNORM, r["rxnorm_code"], r["description"]),
        "subject": {"reference": f"Patient/{r['patient_id']}"},
        "authoredOn": iso(r["start_ts"]),
        "reasonCode": reason,
    })


# --- Load into FHIR -----------------------------------------------------------

def load(resources):
    """PUT resources in batch bundles. Returns {resource id: error} for rejected ones."""
    rejected = {}
    for i in range(0, len(resources), BATCH_SIZE):
        chunk = resources[i:i + BATCH_SIZE]
        bundle = {"resourceType": "Bundle", "type": "batch", "entry": [
            {"resource": r, "request": {"method": "PUT", "url": f"{r['resourceType']}/{r['id']}"}}
            for r in chunk
        ]}
        response = requests.post(FHIR_URL, json=bundle, timeout=600)
        response.raise_for_status()

        # The response has one entry per request entry, in the same order.
        for resource, entry in zip(chunk, response.json()["entry"]):
            result = entry["response"]
            if not result["status"].startswith("2"):
                issue = result.get("outcome", {}).get("issue", [{}])[0]
                rejected[resource["id"]] = issue.get("diagnostics", result["status"])

        done = i + len(chunk)
        print(f"  {chunk[0]['resourceType']}: {done:,} / {len(resources):,}", flush=True)
    return rejected


# --- Main ---------------------------------------------------------------------

with get_connection() as conn:
    conn.row_factory = dict_row
    patients = conn.execute("SELECT * FROM legacy.patients ORDER BY patient_id").fetchall()
    allergies = conn.execute("SELECT * FROM legacy.allergies ORDER BY allergy_id").fetchall()
    medications = conn.execute("SELECT * FROM legacy.medications ORDER BY medication_id").fetchall()
    # Client decisions from the normalization workbook (Phase 5), if any yet
    has_decisions = conn.execute("SELECT to_regclass('migration.decisions')").fetchone()
    decisions = {}
    if has_decisions["to_regclass"]:
        for d in conn.execute("SELECT * FROM migration.decisions"):
            decisions[(d["source_table"], d["source_id"])] = d

patient_ids = {r["patient_id"] for r in patients}
quarantine = []  # (source_table, source_id, reason, detail)
to_load = {"patients": [], "allergies": [], "medications": []}  # (source_id, resource)

def apply_decision(table, source_id, r):
    """Apply the client's decision to a legacy row. None means it was excluded.
    The legacy data itself is never changed; only this in-memory copy."""
    d = decisions.get((table, str(source_id)))
    if d is None:
        return r
    if d["decision"] == "EXCLUDE":
        quarantine.append((table, source_id, "EXCLUDED",
                           f"{d['reason']} (approved by {d['decided_by']})"))
        return None
    if d["decision"] == "RELINK":
        return {**r, "patient_id": d["patient_id"]}
    return {**r, "code": d["code"], "code_system": d["code_system"]}  # APPROVE / CHANGE

for r in patients:
    to_load["patients"].append((r["patient_id"], to_patient(r)))

for r in allergies:
    r = apply_decision("allergies", r["allergy_id"], r)
    if r is None:
        continue
    if r["patient_id"] not in patient_ids:
        quarantine.append(("allergies", r["allergy_id"], "PATIENT_NOT_FOUND", r["patient_id"]))
    elif not r["code"]:
        quarantine.append(("allergies", r["allergy_id"], "ALLERGY_CODE_MISSING", r["description"]))
    elif code_system(r["code_system"], r["code"]) is None:
        quarantine.append(("allergies", r["allergy_id"], "UNKNOWN_CODE_SYSTEM",
                           f"{r['code_system']}: {r['code']} {r['description']}"))
    else:
        to_load["allergies"].append((r["allergy_id"], to_allergy(r)))

for r in medications:
    r = apply_decision("medications", r["medication_id"], r)
    if r is None:
        continue
    if r["patient_id"] not in patient_ids:
        quarantine.append(("medications", r["medication_id"], "PATIENT_NOT_FOUND", r["patient_id"]))
    else:
        to_load["medications"].append((r["medication_id"], to_medication(r)))

# Patients first, so allergies and medications can reference them.
loaded = {}
for table, items in to_load.items():
    rejected = load([resource for _, resource in items])
    for source_id, resource in items:
        if resource["id"] in rejected:
            quarantine.append((table, source_id, "FHIR_REJECTED", rejected[resource["id"]]))
    loaded[table] = len(items) - len(rejected)

with get_connection() as conn:  # replace last run's quarantine in one transaction
    conn.execute("TRUNCATE migration.quarantine")
    conn.cursor().executemany(
        "INSERT INTO migration.quarantine VALUES (%s, %s, %s, %s)", quarantine)

sources = {"patients": patients, "allergies": allergies, "medications": medications}
for table, rows in sources.items():
    held = sum(1 for q in quarantine if q[0] == table)
    ok = "OK" if len(rows) == loaded[table] + held else "MISMATCH"
    print(f"{table:<12} {len(rows):>7,} source {loaded[table]:>7,} loaded {held:>4} quarantined  {ok}")