"""
Read the completed normalization workbook and save the client's decisions.

Valid rows are saved to migration.decisions (replacing earlier decisions).
Invalid rows are reported and not saved. Blank rows stay quarantined.
"""

import pandas as pd
from codes import CODE_SYSTEMS
from db import get_connection

WORKBOOK = 'normalization/normalization_workbook.xlsx'

def read_sheet(name):
    """Read a sheet as text, with blanks as None and decisions in capitals."""
    df = pd.read_excel(WORKBOOK, sheet_name=name, dtype=str)
    df = df.apply(lambda col: col.str.strip()).astype(object).where(df.notna(), None)
    df["decision"] = df["decision"].str.upper()
    return df.to_dict("records")

allergies = read_sheet("Allergy codes")
medications = read_sheet("Orphaned medications")

with get_connection() as conn:
    patient_ids = {r[0] for r in conn.execute("SELECT patient_id FROM legacy.patients")}

decisions, errors, blank = [], [], 0
# Each decision: (source_table, source_id, decision, code, code_system, patient_id, reason, decided_by)

for r in allergies:
    row = f"Allergy {r['allergy_id']}"
    if r["decision"] is None:
        blank += 1
    elif r["decision"] == "APPROVE":
        decisions.append(("allergies", r["allergy_id"], "APPROVE", r["suggested_code"],
                          r["suggested_system"], None, None, r["reviewed_by"]))
    elif r["decision"] == "CHANGE":
        if not r["final_code"] or r["final_system"] not in CODE_SYSTEMS:
            errors.append(f"{row}: CHANGE needs final_code and final_system "
                          f"({' or '.join(CODE_SYSTEMS)})")
        else:
            decisions.append(("allergies", r["allergy_id"], "CHANGE", r["final_code"],
                              r["final_system"], None, None, r["reviewed_by"]))
    else:
        errors.append(f"{row}: decision must be APPROVE or CHANGE, not '{r['decision']}'")

for r in medications:
    row = f"Medication {r['medication_id']}"
    if r["decision"] is None:
        blank += 1
    elif r["decision"] == "RELINK":
        if r["correct_patient_id"] not in patient_ids:
            errors.append(f"{row}: RELINK needs an existing patient, "
                          f"'{r['correct_patient_id']}' not found")
        else:
            decisions.append(("medications", r["medication_id"], "RELINK", None, None,
                              r["correct_patient_id"], None, r["approved_by"]))
    elif r["decision"] == "EXCLUDE":
        if not r["reason"] or not r["approved_by"]:
            errors.append(f"{row}: EXCLUDE needs a reason and approved_by")
        else:
            decisions.append(("medications", r["medication_id"], "EXCLUDE", None, None,
                              None, r["reason"], r["approved_by"]))
    else:
        errors.append(f"{row}: decision must be RELINK or EXCLUDE, not '{r['decision']}'")

with get_connection() as conn:  # replace any earlier decisions in one transaction
    conn.execute("""
        CREATE TABLE IF NOT EXISTS migration.decisions (
            source_table TEXT NOT NULL,
            source_id    TEXT NOT NULL,
            decision     TEXT NOT NULL,  -- APPROVE, CHANGE, RELINK, EXCLUDE
            code         TEXT,           -- APPROVE / CHANGE
            code_system  TEXT,           -- APPROVE / CHANGE: SNOMED-CT or RxNorm
            patient_id   TEXT,           -- RELINK
            reason       TEXT,           -- EXCLUDE
            decided_by   TEXT,
            PRIMARY KEY (source_table, source_id)
        )""")
    conn.execute("DELETE FROM migration.decisions")
    conn.cursor().executemany(
        "INSERT INTO migration.decisions VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", decisions)

counts = pd.Series([d[2] for d in decisions]).value_counts().to_dict() if decisions else {}
summary = ", ".join(f"{n} {d}" for d, n in counts.items()) or "none"
print(f"Saved {len(decisions)} decisions ({summary}); {len(errors)} errors, {blank} blank")
for e in errors:
    print(f"  ERROR {e}")