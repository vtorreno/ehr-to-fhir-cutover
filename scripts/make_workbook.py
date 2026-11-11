"""
Turn the quarantine table into the normalization workbook for the client.
"""

import os
import pandas as pd
from codes import SYSTEM_NAMES, code_system
from db import get_engine

OUTPUT = 'normalization/normalization_workbook.xlsx'

# Refuse to overwrite: the client may already have filled it in.
if os.path.exists(OUTPUT):
    raise SystemExit(f"{OUTPUT} already exists. Delete it first to regenerate.")

engine = get_engine()

# One row per uncoded allergy. The suggestion is the most common code among
# other allergies with exactly the same description.
allergies = pd.read_sql("""
    SELECT a.allergy_id, a.patient_id, a.description,
           s.code AS suggested_code, s.code_system AS legacy_system
    FROM migration.quarantine q
    JOIN legacy.allergies a ON a.allergy_id::text = q.source_id
    LEFT JOIN LATERAL (
        SELECT b.code, b.code_system
        FROM legacy.allergies b
        WHERE b.description = a.description AND b.code IS NOT NULL
        GROUP BY b.code, b.code_system
        ORDER BY count(*) DESC, b.code
        LIMIT 1
    ) s ON true
    WHERE q.source_table = 'allergies' AND q.reason = 'ALLERGY_CODE_MISSING'
    ORDER BY a.allergy_id
""", engine)

allergies["suggested_system"] = [
    SYSTEM_NAMES.get(code_system(system, code)) if code else None
    for system, code in zip(allergies["legacy_system"], allergies["suggested_code"])
]
allergies = allergies.drop(columns="legacy_system")
allergies[["decision", "final_code", "final_system", "reviewed_by"]] = None

# One row per medication that points to a patient who doesn't exist.
medications = pd.read_sql("""
    SELECT m.medication_id, m.description, m.start_ts::date AS start_date,
           m.patient_id AS orphan_patient_id
    FROM migration.quarantine q
    JOIN legacy.medications m ON m.medication_id::text = q.source_id
    WHERE q.source_table = 'medications' AND q.reason = 'PATIENT_NOT_FOUND'
    ORDER BY m.medication_id
""", engine)
medications[["decision", "correct_patient_id", "reason", "approved_by"]] = None

instructions = pd.DataFrame({"Instructions": [
    "Review every row on the two sheets and fill in the empty columns.",
    "",
    "Allergy codes:",
    "  APPROVE = use the suggested code and system.",
    "  CHANGE  = use final_code and final_system instead (SNOMED-CT or RxNorm).",
    "",
    "Orphaned medications:",
    "  RELINK  = attach to correct_patient_id (must be an existing patient).",
    "  EXCLUDE = do not migrate; reason and approved_by are required.",
    "",
    "Rows left blank stay in quarantine, and the cutover stays BLOCKED.",
]})

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
temp = OUTPUT.replace(".xlsx", ".tmp.xlsx")  # renamed once complete, so a crash never leaves a half-written workbook
with pd.ExcelWriter(temp, engine="openpyxl") as writer:
    sheets = {"Instructions": instructions, "Allergy codes": allergies,
              "Orphaned medications": medications}
    for name, df in sheets.items():
        df.to_excel(writer, sheet_name=name, index=False)
        for column in writer.sheets[name].columns:  # widen columns to fit
            width = max(len(str(cell.value or "")) for cell in column)
            writer.sheets[name].column_dimensions[column[0].column_letter].width = width + 2
os.replace(temp, OUTPUT)

print(f"{OUTPUT}: {len(allergies)} allergy rows, {len(medications)} medication rows")