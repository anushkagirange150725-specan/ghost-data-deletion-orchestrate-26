import csv, json, os, sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KEYS = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")
PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]


def load(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(fh)}


def well_formed(steps):
    """step_no is 1..n and phases never go backwards."""
    nums = [s["step_no"] for s in steps] == list(range(1, len(steps) + 1))
    ranks = [PHASES.index(s["phase"]) for s in steps if s["phase"] in PHASES]
    return nums and len(ranks) == len(steps) and ranks == sorted(ranks)


def score(gold, pred):
    m = Counter()
    wrong = []
    for cid, (gs, gsteps) in gold.items():
        ps, psteps = pred.get(cid, ("MISSING", []))
        g = [tuple(s[k] for k in KEYS) for s in gsteps]
        p = [tuple(s[k] for k in KEYS) for s in psteps]
        hit = sum((Counter(g) & Counter(p)).values())
        m["tp"] += hit
        m["fp"] += len(p) - hit
        m["fn"] += len(g) - hit
        m["status"] += gs == ps
        m["exact"] += gs == ps and g == p
        m["sequence"] += [x[:4] for x in g] == [x[:4] for x in p]
        m["well_formed"] += well_formed(psteps)
        for i in range(max(len(g), len(p))):
            m["positions"] += 1
            for j, k in enumerate(KEYS):
                m["field_" + k] += i < len(g) and i < len(p) and g[i][j] == p[i][j]
        if not (gs == ps and g == p):
            wrong.append((cid, gs, ps, g, p))
    n = max(len(gold), 1)
    prec = m["tp"] / (m["tp"] + m["fp"]) if m["tp"] + m["fp"] else 1.0 if not m["fn"] else 0.0
    rec = m["tp"] / (m["tp"] + m["fn"]) if m["tp"] + m["fn"] else 1.0
    out = {"cases": len(gold), "status_accuracy": m["status"] / n, "exact_rows": m["exact"] / n,
           "sequence_accuracy": m["sequence"] / n, "well_formed": m["well_formed"] / n,
           "step_precision": prec, "step_recall": rec, "step_f1": 2 * prec * rec / max(prec + rec, 1e-9)}
    for k in KEYS:
        out["field_" + k] = m["field_" + k] / max(m["positions"], 1)
    return out, wrong


def main(verbose):
    gold = load(os.path.join(ROOT, "dataset", "sample_output.csv"))
    pred = load(os.path.join(ROOT, "code", "evaluation", "sample_predictions.csv"))
    out, wrong = score(gold, pred)
    if verbose:
        for cid, gs, ps, g, p in sorted(wrong, key=lambda w: int(w[0].split("_")[1])):
            print(f"--- {cid} gold={gs} pred={ps}")
            for x in sorted(set(g) - set(p)):
                print("   missing", x)
            for x in sorted(set(p) - set(g)):
                print("   extra  ", x)
    print(f"status accuracy {out['status_accuracy']:.3f} | exact rows {out['exact_rows']:.3f} | "
          f"step precision {out['step_precision']:.3f} recall {out['step_recall']:.3f} F1 {out['step_f1']:.3f}")
    print(f"sequence accuracy {out['sequence_accuracy']:.3f} | well-formed rows {out['well_formed']:.3f}")
    print("field accuracy (by position): " + " | ".join(f"{k} {out['field_' + k]:.3f}" for k in KEYS))
    return out


if __name__ == "__main__":
    main("-v" in sys.argv)