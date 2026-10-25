import argparse, csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auditor.data import REPO, load
from auditor.engine import Auditor
from auditor.checks import subject_checks


def run(requests_file, out_path):
    auditor = Auditor()
    auditor.prepare(load("sample_deletion_requests.csv") + load("deletion_requests.csv"))
    rows = []
    for case in load(requests_file):
        status, steps = auditor.audit(case)
        rows.append({"case_id": case["case_id"], "deletion_status": status,
                     "steps_json": json.dumps(steps, separators=(",", ":"), ensure_ascii=False)})
    rows.sort(key=lambda r: int(r["case_id"].split("_")[1]))
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["case_id", "deletion_status", "steps_json"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out_path}")
    checks = subject_checks(auditor)
    path = os.path.join(REPO, "code", "evaluation", "subject_checks.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(checks[0]))
        w.writeheader()
        w.writerows(checks)
    flagged = sum(1 for r in checks if r["flags"])
    print(f"wrote {len(checks)} subject checks ({flagged} flagged) to {path}")
    path = os.path.join(REPO, "code", "evaluation", "ocr_repairs.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file_id", "resource_id", "ocr_text", "candidate", "decision"])
        w.writeheader()
        w.writerows(auditor.art.repairs)
    print(f"wrote {len(auditor.art.repairs)} OCR repair decisions to {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", action="store_true")
    a = ap.parse_args()
    if a.samples:
        run("sample_deletion_requests.csv", os.path.join(REPO, "code", "evaluation", "sample_predictions.csv"))
    else:
        run("deletion_requests.csv", os.path.join(REPO, "output.csv"))