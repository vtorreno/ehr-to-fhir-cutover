DROP SCHEMA IF EXISTS legacy CASCADE;   -- rerunnable
CREATE SCHEMA legacy;

CREATE TABLE legacy.patients (
    patient_id   TEXT PRIMARY KEY,      -- Synthea Id (UUID)
    first_name   TEXT,
    last_name    TEXT,
    birth_date   DATE,                  -- nullable on purpose
    death_date   DATE,
    gender       TEXT,                  -- 'M' / 'F'
    ssn          TEXT,                  -- synthetic; used for duplicate detection
    address      TEXT,
    city         TEXT,
    state        TEXT,
    zip          TEXT
);

CREATE TABLE legacy.allergies (
    allergy_id     SERIAL PRIMARY KEY,  -- surrogate key (Synthea has none)
    patient_id     TEXT,                -- no FK: never enforced
    encounter_id   TEXT,
    start_date     DATE,
    stop_date      DATE,
    code           TEXT,                -- SNOMED or RxNorm
    code_system    TEXT,                -- as Synthea writes it, e.g. 'SNOMED-CT', 'RxNorm'
    description    TEXT,
    allergy_type   TEXT,                -- allergy | intolerance
    category       TEXT,                -- food | medication | environment
    reaction_code  TEXT,
    reaction_desc  TEXT,
    severity       TEXT                 -- MILD | MODERATE | SEVERE
);

CREATE TABLE legacy.medications (
    medication_id  SERIAL PRIMARY KEY,
    patient_id     TEXT,                -- no FK: never enforced
    encounter_id   TEXT,
    start_ts       TIMESTAMPTZ,
    stop_ts        TIMESTAMPTZ,         -- NULL = still active
    rxnorm_code    TEXT,
    description    TEXT,
    reason_code    TEXT,
    reason_desc    TEXT
);