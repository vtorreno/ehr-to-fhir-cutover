# Cutover Readiness Report

**Verdict: BLOCKED** · 2026-11-11 04:44:04 · 2 Critical checks failed

## Critical checks (any failure blocks go-live)

| Check | Status | Result |
|---|---|---|
| C1 Patients reconciled | ✅ PASS | 1,147 / 1,147 accounted for |
| C2 Allergies reconciled | ❌ FAIL | 5 unresolved (0 missing with no quarantine record) |
| C3 Medications reconciled | ❌ FAIL | 5 unresolved (0 missing with no quarantine record) |
| C4 Allergies and medications coded | ✅ PASS | 0 without a code |
| C5 Links resolve | ✅ PASS | 0 without a valid patient |
| C6 Values match | ✅ PASS | 3 / 3 value sets match |
| C7 Spot check | ✅ PASS | 20 / 20 match the source |

## Must review before go-live (High, doesn't block)

- **Possible duplicate patients:** Otriz / Ortiz, Rayn / Ryan

## Cleanup after go-live (Low, doesn't block)

- **Missing birthdates:** 5 (source: 5)
- **Unspecific allergies (allergen not named):** 209

## Quarantine

- allergies: ALLERGY_CODE_MISSING = 5
- medications: PATIENT_NOT_FOUND = 5

## To unblock

- **C2 Allergies reconciled:** 927, 954, 1041, 389, 379
- **C3 Medications reconciled:** 55928, 17070, 31770, 26386, 22419

Quarantined allergies and medications are resolved by the client in `normalization/normalization_workbook.xlsx`. Any other failure is a migration bug: fix it and rerun.
