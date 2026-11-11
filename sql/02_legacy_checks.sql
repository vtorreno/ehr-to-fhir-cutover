-- Critical: allergies with no code → 5
SELECT count(*) FROM legacy.allergies WHERE code IS NULL OR code = '';

-- Critical: medications pointing at no patient → 5
SELECT count(*)
FROM legacy.medications m
LEFT JOIN legacy.patients p ON p.patient_id = m.patient_id
WHERE p.patient_id IS NULL;

-- Low: patients missing birthdate → 5
SELECT count(*) FROM legacy.patients WHERE birth_date IS NULL;

-- High: likely duplicates (same DOB + SSN) → 2 groups
SELECT birth_date, ssn, array_agg(first_name || ' ' || last_name) AS names
FROM legacy.patients
WHERE birth_date IS NOT NULL
GROUP BY birth_date, ssn
HAVING count(*) > 1;