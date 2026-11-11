"""
Validate the migration by clinical risk. Reads HAPI directly; never the answer key.
"""

import json
import os
import random
import requests
from collections import Counter
from datetime import datetime
from psycopg.rows import dict_row
from db import get_connection

FHIR_URL = os.environ["FHIR_URL"]
OUTPUT = "reports/validation.json"
GENDERS = {"M": "male", "F": "female"}
UNSPECIFIC_ALLERGY = "609328004"  # Allergic disposition (finding)

checks = []

def add(check_id, name, tier, status, actual, expected="", records=()):
    checks.append({"id": check_id, "tier": tier, "name": name, "status": status,
                   "expected": expected, "actual": actual, "records": list(records)})

# --- Read the target (HAPI) ---------------------------------------------------

def fetch_all(resource_type, elements):
    """Every resource of one type, with only the listed fields. Follows paging."""
    found = {}
    url = f"{FHIR_URL}/{resource_type}"
    params = {"_elements": elements, "_count": 200}
    while url:
        response = requests.get(url, params=params, timeout=120)
        response.raise_for_status()
        bundle = response.json()
        for entry in bundle.get("entry", []):
            found[entry["resource"]["id"]] = entry["resource"]
        url = next((link["url"] for link in bundle.get("link", [])
                    if link["relation"] == "next"), None)
        params = None  # the next link already carries the query
    return found

def first_code(concept):
    return ((concept or {}).get("coding") or [{}])[0].get("code")

def reference(resource, field):
    return (resource.get(field) or {}).get("reference")

print("Reading HAPI...")
hapi_patients = fetch_all("Patient", "gender,birthDate,identifier,name")
hapi_allergies = fetch_all("AllergyIntolerance", "code,patient,clinicalStatus")
hapi_meds = fetch_all("MedicationRequest", "medicationCodeableConcept,subject,status")

# --- Read the source (legacy) and the quarantine -------------------------------

with get_connection() as conn:
    conn.row_factory = dict_row
    patients = conn.execute("SELECT * FROM legacy.patients").fetchall()
    allergies = conn.execute("SELECT * FROM legacy.allergies").fetchall()
    medications = conn.execute("SELECT * FROM legacy.medications").fetchall()
    quarantine = conn.execute("SELECT * FROM migration.quarantine").fetchall()

held = {(q["source_table"], q["source_id"]): q["reason"] for q in quarantine}

def reconcile(check_id, name, table, rows, key, fhir_id, hapi):
    """Critical: every source record is in HAPI or EXCLUDED with sign-off."""
    unresolved, silent = [], []
    for r in rows:
        source_id = str(r[key])
        if fhir_id(r) in hapi or held.get((table, source_id)) == "EXCLUDED":
            continue
        unresolved.append(source_id)
        if (table, source_id) not in held:
            silent.append(source_id)  # missing with no quarantine record: a bug
    status = "FAIL" if unresolved else "PASS"
    actual = (f"{len(unresolved)} unresolved ({len(silent)} missing with no quarantine record)"
              if unresolved else f"{len(rows):,} / {len(rows):,} accounted for")
    add(check_id, name, "critical", status, actual, "0 unresolved", unresolved)

# --- Critical -----------------------------------------------------------------

reconcile("C1", "Patients reconciled", "patients", patients, "patient_id",
          lambda r: r["patient_id"], hapi_patients)
reconcile("C2", "Allergies reconciled", "allergies", allergies, "allergy_id",
          lambda r: f"legacy-allergy-{r['allergy_id']}", hapi_allergies)
reconcile("C3", "Medications reconciled", "medications", medications, "medication_id",
          lambda r: f"legacy-med-{r['medication_id']}", hapi_meds)

uncoded = ([i for i, a in hapi_allergies.items() if not first_code(a.get("code"))]
           + [i for i, m in hapi_meds.items()
              if not first_code(m.get("medicationCodeableConcept"))])
add("C4", "Allergies and medications coded", "critical",
    "FAIL" if uncoded else "PASS", f"{len(uncoded)} without a code", "0", uncoded)

patient_refs = {f"Patient/{i}" for i in hapi_patients}
broken = ([i for i, a in hapi_allergies.items() if reference(a, "patient") not in patient_refs]
          + [i for i, m in hapi_meds.items() if reference(m, "subject") not in patient_refs])
add("C5", "Links resolve", "critical", "FAIL" if broken else "PASS",
    f"{len(broken)} without a valid patient", "0", broken)

# Value counts: what the source says vs what HAPI holds (for records that loaded)
loaded_allergies = [a for a in allergies if f"legacy-allergy-{a['allergy_id']}" in hapi_allergies]
loaded_meds = [m for m in medications if f"legacy-med-{m['medication_id']}" in hapi_meds]
comparisons = {
    "gender": (Counter(GENDERS.get(p["gender"], "unknown") for p in patients),
               Counter(p.get("gender") for p in hapi_patients.values())),
    "allergy status": (Counter("resolved" if a["stop_date"] else "active" for a in loaded_allergies),
                       Counter(first_code(a.get("clinicalStatus")) for a in hapi_allergies.values())),
    "medication status": (Counter("completed" if m["stop_ts"] else "active" for m in loaded_meds),
                          Counter(m.get("status") for m in hapi_meds.values())),
}
mismatched = [f"{name}: source {dict(src)} vs HAPI {dict(tgt)}"
              for name, (src, tgt) in comparisons.items() if src != tgt]
add("C6", "Values match", "critical", "FAIL" if mismatched else "PASS",
    f"{len(comparisons) - len(mismatched)} / {len(comparisons)} value sets match",
    "all match", mismatched)

# Spot check: 20 records (same 20 every run), full resource fetched from HAPI
rng = random.Random(11)
sample = ([("Patient", p["patient_id"], p) for p in rng.sample(patients, 7)]
          + [("AllergyIntolerance", f"legacy-allergy-{a['allergy_id']}", a)
             for a in rng.sample(loaded_allergies, min(7, len(loaded_allergies)))]
          + [("MedicationRequest", f"legacy-med-{m['medication_id']}", m)
             for m in rng.sample(loaded_meds, min(6, len(loaded_meds)))])
spot_failures = []
for resource_type, fhir_id, row in sample:
    response = requests.get(f"{FHIR_URL}/{resource_type}/{fhir_id}", timeout=60)
    if response.status_code != 200:
        spot_failures.append(f"{fhir_id}: not found")
        continue
    res = response.json()
    if resource_type == "Patient":
        name = (res.get("name") or [{}])[0]
        expected = {"family": row["last_name"], "given": row["first_name"],
                    "birthDate": row["birth_date"].isoformat() if row["birth_date"] else None}
        actual = {"family": name.get("family"), "given": (name.get("given") or [None])[0],
                  "birthDate": res.get("birthDate")}
    elif resource_type == "AllergyIntolerance":
        expected = {"code": row["code"], "patient": f"Patient/{row['patient_id']}"}
        actual = {"code": first_code(res.get("code")), "patient": reference(res, "patient")}
    else:
        expected = {"code": row["rxnorm_code"], "subject": f"Patient/{row['patient_id']}",
                    "status": "completed" if row["stop_ts"] else "active"}
        actual = {"code": first_code(res.get("medicationCodeableConcept")),
                  "subject": reference(res, "subject"), "status": res.get("status")}
    wrong = [field for field in expected if expected[field] != actual[field]]
    if wrong:
        spot_failures.append(f"{fhir_id}: {', '.join(wrong)}")
add("C7", "Spot check", "critical", "FAIL" if spot_failures else "PASS",
    f"{len(sample) - len(spot_failures)} / {len(sample)} match the source",
    "all match", spot_failures)

# --- High: possible duplicate patients (same birthdate + SSN) -------------------

by_identity = {}
for patient_id, p in hapi_patients.items():
    ssn = next((i.get("value") for i in p.get("identifier", [])
                if i.get("system") == "http://hl7.org/fhir/sid/us-ssn"), None)
    if p.get("birthDate") and ssn:
        by_identity.setdefault((p["birthDate"], ssn), []).append(patient_id)
pairs = []
for ids in by_identity.values():
    if len(ids) > 1:
        names = [(hapi_patients[i].get("name") or [{}])[0].get("family", "?") for i in ids]
        pairs.append(ids + [" / ".join(names)])
add("H1", "Possible duplicate patients", "high", "FLAG" if pairs else "PASS",
    f"{len(pairs)} pairs", "listed for review", pairs)

# --- Low: cleanup items ---------------------------------------------------------

no_birthdate = [i for i, p in hapi_patients.items() if not p.get("birthDate")]
source_nulls = sum(1 for p in patients if p["birth_date"] is None)
add("L1", "Missing birthdates", "low", "FLAG" if no_birthdate else "PASS",
    f"{len(no_birthdate)} (source: {source_nulls})", "listed for cleanup", no_birthdate)

unspecific = sum(1 for a in hapi_allergies.values()
                 if first_code(a.get("code")) == UNSPECIFIC_ALLERGY)
add("L2", "Unspecific allergies (allergen not named)", "low",
    "FLAG" if unspecific else "PASS", f"{unspecific}", "listed for cleanup")

# --- Quarantine summary (informational) -------------------------------------------

reasons = Counter(f"{q['source_table']}: {q['reason']}" for q in quarantine)
add("Q", "Quarantine summary", "info", "INFO", f"{len(quarantine)} rows",
    records=[f"{reason} = {n}" for reason, n in sorted(reasons.items())])

# --- Save and print ---------------------------------------------------------------

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, "w") as f:
    json.dump({"run_at": datetime.now().isoformat(timespec="seconds"), "checks": checks},
              f, indent=2)

for c in checks:
    print(f"{c['id']:<3} {c['tier']:<9} {c['status']:<5} {c['name']:<42} {c['actual']}")
print(f"\nSaved {OUTPUT}")