import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from auditor.data import load, ts
from auditor.engine import Auditor

A = Auditor()
A.prepare(load("sample_deletion_requests.csv") + load("deletion_requests.csv"))


def test_unseen_legal_hold_is_retained_not_deleted():
    # legal_hold_1745 appears only in activity, never in a captured file
    assert not A.ev.by_resource.get("legal_hold_1745")
    res = A.state("legal_hold_1745", ts("2026-05-29T08:00:00Z"))
    assert res["category"] == "LEGAL_HOLD_RECORD" and res["present"]


def test_no_retained_record_is_ever_deleted():
    bad = []
    for c in A.cases_all:
        status, steps = A.audit(c)
        for s in steps:
            retained = s["resource_id"].startswith(("legal_hold_", "audit_record_"))
            if retained and s["operation"] in ("DELETE_RECORD", "VERIFY_RECORD_ABSENT"):
                bad.append((c["case_id"], s["resource_id"], s["operation"]))
    assert bad == []


def test_ties_are_symmetric_and_reported():
    for cid, others in A.act.ties.items():
        for o in others:
            assert cid in A.act.ties[o]