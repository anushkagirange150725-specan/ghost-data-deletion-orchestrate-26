import csv, json, os, sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KEYS = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")


def load(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(fh)}


def main(verbose):
    gold = load(os.path.join(ROOT, "dataset", "sample_output.csv"))
    pred = load(os.path.join(ROOT, "code", "evaluation", "sample_predictions.csv"))
    status_ok = exact = tp = fp = fn = 0
    for cid, (gs, gsteps) in sorted(gold.items(), key=lambda kv: int(kv[0].split("_")[1])):
        ps, psteps = pred.get(cid, ("MISSING", []))
        g = [tuple(s[k] for k in KEYS) for s in gsteps]
        p = [tuple(s[k] for k in KEYS) for s in psteps]
        match = sum((Counter(g) & Counter(p)).values())
        tp, fp, fn = tp + match, fp + len(p) - match, fn + len(g) - match
        status_ok += gs == ps
        exact += gs == ps and g == p
        if verbose and not (gs == ps and g == p):
            print(f"--- {cid} gold={gs} pred={ps}")
            for x in sorted(set(g) - set(p)):
                print("   missing", x)
            for x in sorted(set(p) - set(g)):
                print("   extra  ", x)
    prec, rec = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    print(f"status accuracy {status_ok / len(gold):.3f} | exact rows {exact / len(gold):.3f} | "
          f"step precision {prec:.3f} recall {rec:.3f} F1 {2 * prec * rec / max(prec + rec, 1e-9):.3f}")


if __name__ == "__main__":
    main("-v" in sys.argv)