"""
Turn the validation results into a one-page Go/No-Go cutover report.
"""

import json
import shutil

SOURCE = 'reports/validation.json'
WORKBOOK = 'normalization/normalization_workbook.xlsx'
STATUS = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "FLAG": "⚠️ FLAG", "INFO": "ℹ️ INFO"}

data = json.load(open(SOURCE))
checks = data["checks"]

def tier(name):
    return [c for c in checks if c["tier"] == name]

def evidence(c):
    """Short, readable evidence for a flag (names for duplicates, else the count)."""
    if c["id"] == "H1":
        return ", ".join(pair[-1] for pair in c["records"])
    return c["actual"]

failed = [c for c in tier("critical") if c["status"] == "FAIL"]
verdict = "BLOCKED" if failed else "READY"
summary = (f"{len(failed)} Critical check{'s' if len(failed) != 1 else ''} failed"
           if failed else "all Critical checks passed")

lines = [
    "# Cutover Readiness Report",
    "",
    f"**Verdict: {verdict}** · {data['run_at'].replace('T', ' ')} · {summary}",
    "",
    "## Critical checks (any failure blocks go-live)",
    "",
    "| Check | Status | Result |",
    "|---|---|---|",
]
lines += [f"| {c['id']} {c['name']} | {STATUS[c['status']]} | {c['actual']} |"
          for c in tier("critical")]

lines += ["", "## Must review before go-live (High, doesn't block)", ""]
lines += [f"- **{c['name']}:** {evidence(c)}" if c["status"] == "FLAG"
          else f"- {c['name']}: none found" for c in tier("high")]

lines += ["", "## Cleanup after go-live (Low, doesn't block)", ""]
lines += [f"- **{c['name']}:** {c['actual']}" if c["status"] == "FLAG"
          else f"- {c['name']}: none found" for c in tier("low")]

by_id = {c["id"]: c for c in checks}

lines += ["", "## Quarantine", ""]
lines += [f"- {r}" for r in by_id["Q"]["records"]] or ["- Empty"]

if by_id.get("X", {}).get("records"):
    lines += ["", "## Signed-off exclusions (accounted for, not migrated)", ""]
    lines += [f"- {r}" for r in by_id["X"]["records"]]

if failed:
    lines += ["", "## To unblock", ""]
    for c in failed:
        shown = ", ".join(str(r) for r in c["records"][:20])
        more = f" and {len(c['records']) - 20} more" if len(c["records"]) > 20 else ""
        lines.append(f"- **{c['id']} {c['name']}:** {shown}{more}")
    lines += ["", f"Quarantined allergies and medications are resolved by the client in "
                  f"`{WORKBOOK}`. Any other failure is a migration bug: fix it and rerun."]

output = f"reports/cutover_report_{verdict}.md"
with open(output, "w") as f:
    f.write("\n".join(lines) + "\n")
shutil.copy(SOURCE, f"reports/validation_{verdict}.json")  # keep the evidence with the report

print(f"Verdict: {verdict} -> {output}")