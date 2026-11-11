"""
Score validation against the answer key: did it find every injected error?
"""

import json
import sys

checks = {c["id"]: c for c in json.load(open("reports/validation.json"))["checks"]}
errors = json.load(open("data/injected_errors.json"))["errors"]

# What validation found, per check
found = {
    "C2": {str(r) for r in checks["C2"]["records"]},
    "C3": {str(r) for r in checks["C3"]["records"]},
    "L1": set(checks["L1"]["records"]),
    "H1": {patient_id for pair in checks["H1"]["records"] for patient_id in pair[:2]},
}

# Injected error type -> (check that should find it, the ID to look for)
expected_in = {
    "allergy_missing_code": ("C2", lambda e: str(e["record_id"])),
    "orphaned_medication": ("C3", lambda e: str(e["record_id"])),
    "missing_birthdate": ("L1", lambda e: e["patient_id"]),
    "duplicate_patient": ("H1", lambda e: e["patient_id"]),
}

detected, missed = 0, []
injected = {check: set() for check in found}
for e in errors:
    check, key = expected_in[e["type"]]
    injected[check].add(key(e))
    if key(e) in found[check]:
        detected += 1
    else:
        missed.append(f"{e['type']}: {key(e)}")

print(f"Detected {detected} / {len(errors)} injected errors\n")
for error_type, (check, _) in expected_in.items():
    total = sum(1 for e in errors if e["type"] == error_type)
    hits = sum(1 for e in errors if e["type"] == error_type
               and expected_in[error_type][1](e) in found[check])
    print(f"  {error_type:<22} {hits} / {total}  (check {check})")

# False positives: flagged by a check but not injected
print("\nFlagged but not injected (expect 0; anything here is a real problem the injector didn't create, or a validation bug):")
for check, ids in found.items():
    if check == "H1":  # a real duplicate pair contains an injected duplicate
        extra = [p for p in checks["H1"]["records"] if not set(p[:2]) & injected["H1"]]
    else:
        extra = sorted(ids - injected[check])
    print(f"  {check}: {len(extra)}" + (f"  {extra[:5]}" if extra else ""))

if missed:
    print("\nMissed:")
    for m in missed:
        print(f"  {m}")
    sys.exit(1)