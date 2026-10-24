from __future__ import annotations
from .data import load

ORDER = ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK",
         "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD",
         "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED", "VERIFY_RECORD_ANONYMIZED",
         "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED"]
STATE = {"REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT", "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
         "REPORT_RESTORE_RISK": "ACTIVE", "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED",
         "DELETE_RECORD": "ABSENT", "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
         "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT", "VERIFY_RECORD_REDACTED": "REDACTED",
         "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
         "VERIFY_RESTORE_BLOCKED": "BLOCKED"}
PHASE_RANK = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
RULES = {r["data_category"]: r["required_action"] for r in load("deletion_rules.csv")}


def phase(op: str) -> str:
    return "FINDING" if op.startswith("REPORT") else "VERIFICATION" if op.startswith("VERIFY") else "REMEDIATION"


def operations(res) -> list[str]:
    cat = res["category"]
    if cat == "DATA_FLOW":
        return (["REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW"] if res["present"] and res["flow_active"] else []) \
            + ["VERIFY_DATA_FLOW_DISABLED"]
    if cat == "BACKUP_ARCHIVE":
        return (["REPORT_RESTORE_RISK", "BLOCK_RESTORE"] if res["present"] and res["restore_allowed"] else []) \
            + ["VERIFY_RESTORE_BLOCKED"]
    action = RULES.get(cat, "DELETE")
    if action == "RETAIN":
        return ["VERIFY_RECORD_PRESENT"]
    if action == "DELETE":
        return (["REPORT_REMAINING_RECORD", "DELETE_RECORD"] if res["present"] else []) + ["VERIFY_RECORD_ABSENT"]
    if not res["present"]:
        return ["VERIFY_RECORD_ABSENT"]
    fix, check = ("REDACT_RECORD", "VERIFY_RECORD_REDACTED") if action == "REDACT" else \
        ("ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED")
    return (["REPORT_EXPOSED_PII", fix] if res["pii"] else []) + [check]


def build(resources: list[dict]):
    raw = [(op, r) for r in resources for op in operations(r)]
    status = "INCOMPLETE" if any(phase(op) == "FINDING" for op, _ in raw) else "COMPLETE"
    steps = []
    for op, r in raw:
        p = phase(op)
        if status == "COMPLETE" and p != "VERIFICATION":
            continue
        ev = r["evidence"] if (status == "COMPLETE" or p == "FINDING") else ""
        steps.append({"phase": p, "system_id": r["system"], "resource_id": r["resource_id"],
                      "operation": op, "state": STATE[op], "evidence_id": ev or ""})
    steps.sort(key=lambda s: (PHASE_RANK[s["phase"]], ORDER.index(s["operation"]), s["system_id"], s["resource_id"]))
    return status, [{"step_no": i, **s} for i, s in enumerate(steps, 1)]