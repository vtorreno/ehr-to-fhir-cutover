# Cutover Readiness Report

**Verdict: READY** · 2026-11-11 09:32:40 · all Critical checks passed

## Critical checks (any failure blocks go-live)

| Check | Status | Result |
|---|---|---|
| C1 Patients reconciled | ✅ PASS | 1,147 / 1,147 accounted for |
| C2 Allergies reconciled | ✅ PASS | 1,095 / 1,095 accounted for |
| C3 Medications reconciled | ✅ PASS | 56,977 / 56,977 accounted for |
| C4 Allergies and medications coded | ✅ PASS | 0 without a code |
| C5 Links resolve | ✅ PASS | 0 without a valid patient |
| C6 Values match | ✅ PASS | 3 / 3 value sets match |
| C7 Spot check | ✅ PASS | 20 / 20 match the source |

## Must review before go-live (High, doesn't block)

- **Possible duplicate patients:** Otriz / Ortiz, Rayn / Ryan

## Cleanup after go-live (Low, doesn't block)

- **Missing birthdates:** 5 (source: 5)
- **Unspecific allergies (allergen not named):** 210

## Quarantine

- medications: EXCLUDED = 1

## Signed-off exclusions (accounted for, not migrated)

- medications 17070: Original patient record purged; 1995 prescription not relevant to current care (approved by VT)
