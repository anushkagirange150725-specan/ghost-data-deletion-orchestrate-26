"""Check an output file against the challenge's output contract.

Run from the repo root:
    python code/evaluation/validate_output.py                 # output.csv vs deletion_requests.csv
    python code/evaluation/validate_output.py --samples       # sample_predictions.csv vs samples
"""
import csv, json, os, sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "dataset")
PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
ALLOWED = {
    "FINDING": {"REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT",
                "REPORT_ACTIVE_DATA_FLOW": "ACTIVE", "REPORT_RESTORE_RISK": "ACTIVE"},
    "REMEDIATION": {"DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED", "DELETE_RECORD": "ABSENT",
                    "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED"},
    "VERIFICATION": {"VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT",
                     "VERIFY_RECORD_REDACTED": "REDACTED", "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
                     "VERIFY_DATA_FLOW_DISABLED": "DISABLED", "VERIFY_RESTORE_BLOCKED": "BLOCKED"},
}
FIELDS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
# a finding must be followed by its remediation, and a remediation by its verification
NEXT = {"REPORT_ACTIVE_DATA_FLOW": "DISABLE_DATA_FLOW", "REPORT_RESTORE_RISK": "BLOCK_RESTORE",
        "DISABLE_DATA_FLOW": "VERIFY_DATA_FLOW_DISABLED", "BLOCK_RESTORE": "VERIFY_RESTORE_BLOCKED",
        "DELETE_RECORD": "VERIFY_RECORD_ABSENT", "REDACT_RECORD": "VERIFY_RECORD_REDACTED",
        "ANONYMIZE_RECORD": "VERIFY_RECORD_ANONYMIZED"}


def ts(v):
    return datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def rows(name):
    with open(os.path.join(DATA, name) if os.sep not in name else name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def validate(out_path, req_name):
    reqs = {r["case_id"]: r for r in rows(req_name)}
    captured = {r["file_id"]: ts(r["captured_at"]) for r in rows("evidence_files.csv")}
    events = {r["activity_id"]: ts(r["event_time"]) for r in rows("system_activity.csv")}
    audits = {r["audit_id"] for r in rows("user_audit_log.csv")}
    errors = []
    with open(out_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != ["case_id", "deletion_status", "steps_json"]:
            errors.append(f"header is {reader.fieldnames}")
        out = list(reader)
    ids = [r["case_id"] for r in out]
    if sorted(ids) != sorted(reqs):
        errors.append(f"case ids differ: missing {sorted(set(reqs) - set(ids))[:5]} extra {sorted(set(ids) - set(reqs))[:5]}")
    if len(ids) != len(set(ids)):
        errors.append("duplicate case ids")
    if ids != sorted(ids, key=lambda c: int(c.split("_")[1])):
        errors.append("rows are not sorted by case_id")
    for r in out:
        cid, status = r["case_id"], r["deletion_status"]
        bad = lambda msg: errors.append(f"{cid}: {msg}")
        try:
            steps = json.loads(r["steps_json"])
        except json.JSONDecodeError as e:
            bad(f"steps_json is not valid JSON ({e})")
            continue
        if status not in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"):
            bad(f"unknown status {status}")
        if status == "NOT_APPLICABLE" and steps:
            bad("NOT_APPLICABLE must have []")
        if status == "COMPLETE" and any(s.get("phase") != "VERIFICATION" for s in steps):
            bad("COMPLETE may contain only VERIFICATION steps")
        if status == "INCOMPLETE" and not any(s.get("phase") == "FINDING" for s in steps):
            bad("INCOMPLETE has no FINDING")
        if [s.get("step_no") for s in steps] != list(range(1, len(steps) + 1)):
            bad("step_no is not 1..n")
        ranks = [PHASES.index(s["phase"]) if s.get("phase") in PHASES else -1 for s in steps]
        if ranks != sorted(ranks):
            bad("phases out of order")
        audit = ts(reqs[cid]["audit_at"]) if cid in reqs else None
        for s in steps:
            if set(s) != FIELDS:
                bad(f"step {s.get('step_no')} has fields {sorted(s)}")
                continue
            want = ALLOWED.get(s["phase"], {}).get(s["operation"])
            if want is None:
                bad(f"step {s['step_no']}: {s['operation']} not allowed in {s['phase']}")
            elif s["state"] != want:
                bad(f"step {s['step_no']}: {s['operation']} needs state {want}, got {s['state']}")
            ev = s["evidence_id"]
            needs = s["phase"] == "FINDING" or status == "COMPLETE"
            if needs and not ev:
                bad(f"step {s['step_no']}: evidence_id required")
            if not needs and ev:
                bad(f"step {s['step_no']}: future step must have empty evidence_id")
            if ev:
                when = captured.get(ev) or events.get(ev)
                if when is None and ev not in audits:
                    bad(f"step {s['step_no']}: unknown evidence id {ev}")
                elif when and audit and when > audit:
                    bad(f"step {s['step_no']}: cites {ev} captured after audit_at")
        if status == "INCOMPLETE":
            ops = {(s["resource_id"], s["operation"]) for s in steps}
            for rid, op in ops:
                if op in NEXT and (rid, NEXT[op]) not in ops:
                    bad(f"{rid}: {op} without {NEXT[op]}")
            for rid, op in ops:
                if op in ("REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII") and not any(
                        r == rid and o in ("DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD") for r, o in ops):
                    bad(f"{rid}: {op} without remediation")
    return out, errors


def main():
    if "--samples" in sys.argv:
        path, req = os.path.join(ROOT, "code", "evaluation", "sample_predictions.csv"), "sample_deletion_requests.csv"
    else:
        path, req = os.path.join(ROOT, "output.csv"), "deletion_requests.csv"
    out, errors = validate(path, req)
    for e in errors[:50]:
        print("ERROR", e)
    print(f"{os.path.relpath(path, ROOT)}: {len(out)} rows, {len(errors)} contract violations")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
