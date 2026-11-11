"""Load the Synthea CSVs into the legacy schema."""

import pandas as pd
from sqlalchemy import text
from db import get_engine

# Synthea column -> legacy column
COLUMNS = {
    "patients": {
        "Id": "patient_id", "FIRST": "first_name", "LAST": "last_name",
        "BIRTHDATE": "birth_date", "DEATHDATE": "death_date", "GENDER": "gender",
        "SSN": "ssn", "ADDRESS": "address", "CITY": "city", "STATE": "state", "ZIP": "zip",
    },
    "allergies": {
        "PATIENT": "patient_id", "ENCOUNTER": "encounter_id", "START": "start_date",
        "STOP": "stop_date", "CODE": "code", "SYSTEM": "code_system",
        "DESCRIPTION": "description", "TYPE": "allergy_type", "CATEGORY": "category",
        "REACTION1": "reaction_code", "DESCRIPTION1": "reaction_desc", "SEVERITY1": "severity",
    },
    "medications": {
        "PATIENT": "patient_id", "ENCOUNTER": "encounter_id", "START": "start_ts",
        "STOP": "stop_ts", "CODE": "rxnorm_code", "DESCRIPTION": "description",
        "REASONCODE": "reason_code", "REASONDESCRIPTION": "reason_desc",
    },
}

with get_engine().begin() as conn:
    conn.execute(text("TRUNCATE legacy.patients, legacy.allergies, legacy.medications RESTART IDENTITY"))

    for table, mapping in COLUMNS.items():
        df = pd.read_csv(f"data/raw/{table}.csv", usecols=mapping, dtype=str).rename(columns=mapping)

        for col in df.columns:
            if col.endswith("_name"):
                df[col] = df[col].str.rstrip("0123456789")
            elif col.endswith("_date"):
                df[col] = pd.to_datetime(df[col]).dt.date
            elif col.endswith("_ts"):
                df[col] = pd.to_datetime(df[col], utc=True)

        df.to_sql(table, conn, schema="legacy", if_exists="append", index=False)
        print(table, len(df))