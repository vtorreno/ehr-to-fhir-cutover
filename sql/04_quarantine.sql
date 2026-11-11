SET client_min_messages = warning;
DROP SCHEMA IF EXISTS migration CASCADE;
CREATE SCHEMA migration;

CREATE TABLE migration.quarantine (
    source_table  TEXT NOT NULL,   -- 'patients', 'allergies' or 'medications'
    source_id     TEXT NOT NULL,   -- patient_id, allergy_id or medication_id
    reason        TEXT NOT NULL,   -- ALLERGY_CODE_MISSING, PATIENT_NOT_FOUND, UNKNOWN_CODE_SYSTEM, FHIR_REJECTED
    detail        TEXT,            -- e.g. the missing patient_id, or the server's error
    PRIMARY KEY (source_table, source_id)
);