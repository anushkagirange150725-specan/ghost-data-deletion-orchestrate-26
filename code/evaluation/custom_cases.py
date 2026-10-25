"""Custom evaluation cases.

Each scenario copies one solved sample request, changes one input field, and states the answer the
challenge rules require. The changed row replaces the original, the whole pipeline is re-run, and
the result is checked against that expectation.

Run from the repo root:  python code/evaluation/custom_cases.py
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from auditor.data import load, ts
from auditor.engine import Auditor
from evaluate import load as load_output, score

GOLD = load_output(os.path.join(HERE, "..", "..", "dataset", "sample_output.csv"))
CAPTURED = {r["file_id"]: ts(r["captured_at"]) for r in load("evidence_files.csv")}

SCENARIOS = [
    {"id": "C1_current_email_for_old_email_case",
     "why": "case_29 was filed from the user's OLD e-mail. The same request from the CURRENT e-mail "
            "must resolve to the same person (user_29) and give exactly the same answer.",
     "base": "case_29", "change": {"email": "noah.f4380@outlook.com"}, "expect": "same_as_gold"},
    {"id": "C2_same_intent_in_german",
     "why": "case_21 rewritten in German with the same meaning must be audited exactly like the original.",
     "base": "case_21", "change": {"request_text": "Bitte löschen Sie mein Konto und alle meine persönlichen Daten."},
     "expect": "same_as_gold"},
    {"id": "C3_forged_account_do_not_delete_yet",
     "why": "The subject reports that someone forged an account and asks NOT to delete it yet "
            "(needed for a police report). That does not authorise deletion -> NOT_APPLICABLE, no steps.",
     "base": "case_21",
     "change": {"request_text": "Someone opened this account using my email. Please do not delete it yet, "
                                "I need the records for a police report."},
     "expect": ("NOT_APPLICABLE", [])},
    {"id": "C4_lookalike_email_is_not_the_subject",
     "why": "case_28 filed from the look-alike smartinez6461.jr@gmail.com, an address that only appears "
            "on a stranger's search record. It matches no known subject, so nobody's data may be audited "
            "or deleted -> NOT_APPLICABLE, and user_28's records must not appear.",
     "base": "case_28", "change": {"email": "smartinez6461.jr@gmail.com"}, "expect": ("NOT_APPLICABLE", [])},
    {"id": "C5_messy_but_exact_email",
     "why": "case_31 filed as 'mailto:A.EZE08@GMAIL.COM ' (prefix, capitals, trailing space) is still "
            "exactly the subject's address and must give the identical answer.",
     "base": "case_31", "change": {"email": "mailto:A.EZE08@GMAIL.COM "}, "expect": "same_as_gold"},
    {"id": "C6_audit_before_key_capture",
     "why": "case_24's findings cite evidence_92 (captured 2026-09-15 11:44:55). With audit_at moved to "
            "11:00 that capture is in the future, so no step may cite it or any later capture.",
     "base": "case_24", "change": {"audit_at": "2026-09-15T11:00:00Z"}, "expect": "no_late_evidence"},
]


def run(auditor, sc):
    rows = []
    for r in load("sample_deletion_requests.csv"):
        if r["case_id"] == sc["base"]:
            r = dict(r, **sc["change"])
        rows.append(r)
    auditor.prepare(rows + load("deletion_requests.csv"))
    case = next(c for c in auditor.cases_all if c["case_id"] == sc["base"])
    status, steps = auditor.audit(case)
    return case, status, steps


def check(sc, case, status, steps):
    exp = sc["expect"]
    if exp == "no_late_evidence":
        late = [s["evidence_id"] for s in steps
                if s["evidence_id"] in CAPTURED and CAPTURED[s["evidence_id"]] > ts(case["audit_at"])]
        return not late, f"late citations={late} status={status} steps={len(steps)}"
    if exp == "same_as_gold":
        exp = GOLD[sc["base"]]
    out, _ = score({"x": exp}, {"x": (status, steps)})
    ok = out["exact_rows"] == 1.0
    return ok, f"status={status} (want {exp[0]}) step F1={out['step_f1']:.3f} exact={ok}"


def main():
    auditor = Auditor()
    results = []
    for sc in SCENARIOS:
        case, status, steps = run(auditor, sc)
        ok, detail = check(sc, case, status, steps)
        results.append((sc, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {sc['id']}: {detail}")
    print(f"\n{sum(ok for _, ok, _ in results)}/{len(results)} custom cases passed")
    return results


if __name__ == "__main__":
    main()