import json
import random
import uuid
from db import get_connection

SEED = 11
rng = random.Random(SEED)  # same seed -> same records broken every run
used = set()               # patients already involved, so no patient gets two errors
errors = []


def pick(rows, n, patient_col=1):
    """Randomly pick n rows belonging to n different, unused patients."""
    chosen = []
    for row in rng.sample(rows, len(rows)):
        if row[patient_col] not in used:
            used.add(row[patient_col])
            chosen.append(row)
            if len(chosen) == n:
                return chosen
    raise SystemExit("Not enough eligible rows")


def new_id():
    """Random but reproducible UUID (comes from the seeded rng)."""
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def typo(name):
    """Swap the first pair of different adjacent letters: Parker -> Praker."""
    for i in range(1, len(name) - 1):
        if name[i] != name[i + 1]:
            return name[:i] + name[i + 1] + name[i] + name[i + 2:]
    return name + name[-1]


with get_connection() as conn:  # one transaction: all 17 errors, or none
    already_broken = conn.execute("""
        SELECT (SELECT count(*) FROM legacy.allergies WHERE code IS NULL)
             + (SELECT count(*) FROM legacy.patients WHERE birth_date IS NULL)
    """).fetchone()[0]
    if already_broken:
        raise SystemExit("Errors already present. Run load_legacy.py first.")

    # 1. Critical: 5 allergies lose their code (description is kept)
    rows = conn.execute("""
        SELECT allergy_id, patient_id, code, code_system, description
        FROM legacy.allergies ORDER BY allergy_id
    """).fetchall()
    for allergy_id, patient_id, code, system, description in pick(rows, 5):
        conn.execute("UPDATE legacy.allergies SET code = NULL, code_system = NULL "
                     "WHERE allergy_id = %s", (allergy_id,))
        errors.append({"type": "allergy_missing_code", "tier": "critical",
                       "table": "allergies", "record_id": allergy_id,
                       "patient_id": patient_id, "description": description,
                       "original_code": code, "original_system": system})

    # 2. Critical: 5 medications point to a patient that doesn't exist
    rows = conn.execute("""
        SELECT medication_id, patient_id, description
        FROM legacy.medications ORDER BY medication_id
    """).fetchall()
    for medication_id, patient_id, description in pick(rows, 5):
        orphan_id = new_id()
        conn.execute("UPDATE legacy.medications SET patient_id = %s "
                     "WHERE medication_id = %s", (orphan_id, medication_id))
        errors.append({"type": "orphaned_medication", "tier": "critical",
                       "table": "medications", "record_id": medication_id,
                       "description": description,
                       "original_patient_id": patient_id,
                       "orphan_patient_id": orphan_id})

    # 3. Low: 5 patients lose their birthdate
    rows = conn.execute("""
        SELECT patient_id, birth_date FROM legacy.patients ORDER BY patient_id
    """).fetchall()
    for patient_id, birth_date in pick(rows, 5, patient_col=0):
        conn.execute("UPDATE legacy.patients SET birth_date = NULL "
                     "WHERE patient_id = %s", (patient_id,))
        errors.append({"type": "missing_birthdate", "tier": "low",
                       "table": "patients", "patient_id": patient_id,
                       "original_birth_date": str(birth_date)})

    # 4. High: 2 patients re-registered with a typo in the last name
    rows = conn.execute("""
        SELECT patient_id, last_name FROM legacy.patients ORDER BY patient_id
    """).fetchall()
    for patient_id, last_name in pick(rows, 2, patient_col=0):
        duplicate_id, misspelled = new_id(), typo(last_name)
        conn.execute("""
            INSERT INTO legacy.patients
            SELECT %s, first_name, %s, birth_date, death_date, gender,
                   ssn, address, city, state, zip
            FROM legacy.patients WHERE patient_id = %s
        """, (duplicate_id, misspelled, patient_id))
        errors.append({"type": "duplicate_patient", "tier": "high",
                       "table": "patients", "patient_id": duplicate_id,
                       "duplicate_of": patient_id,
                       "typo": f"{last_name} -> {misspelled}"})

with open("data/injected_errors.json", "w") as f:
    json.dump({"seed": SEED, "total": len(errors), "errors": errors}, f, indent=2)

print(f"Injected {len(errors)} errors -> data/injected_errors.json")