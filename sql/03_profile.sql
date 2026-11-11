-- Row counts
SELECT 'patients', count(*) FROM legacy.patients
UNION ALL SELECT 'allergies', count(*) FROM legacy.allergies
UNION ALL SELECT 'medications', count(*) FROM legacy.medications;

-- Every distinct value that needs a FHIR equivalent
SELECT gender, count(*)       FROM legacy.patients  GROUP BY 1;
SELECT code_system, count(*)  FROM legacy.allergies GROUP BY 1;
SELECT allergy_type, count(*) FROM legacy.allergies GROUP BY 1;
SELECT category, count(*)     FROM legacy.allergies GROUP BY 1;
SELECT severity, count(*)     FROM legacy.allergies GROUP BY 1;

-- Missing values
SELECT count(*) FILTER (WHERE birth_date IS NULL) AS no_birthdate FROM legacy.patients;
SELECT count(*) FILTER (WHERE code IS NULL)        AS no_code      FROM legacy.allergies;
SELECT count(*) FILTER (WHERE rxnorm_code IS NULL) AS no_code      FROM legacy.medications;

-- Allergy descriptions with their codes (used by the workbook later)
SELECT description, code, count(*) FROM legacy.allergies GROUP BY 1, 2 ORDER BY 1;