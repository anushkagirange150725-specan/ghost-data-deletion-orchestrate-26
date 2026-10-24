import csv, json, os, collections

D = os.path.join(os.path.dirname(__file__), "..", "dataset")
rd = lambda f: list(csv.DictReader(open(os.path.join(D, f), encoding="utf-8")))

reqs = {r["case_id"]: r for r in rd("sample_deletion_requests.csv")}
for r in rd("sample_output.csv"):
    q = reqs[r["case_id"]]
    print(f"=== {r['case_id']} {r['deletion_status']} | {q['email']} | req {q['requested_at']} "
          f"| claimed {q['reported_status']} | audit {q['audit_at']}")
    print("    text:", q["request_text"][:120])
    for s in json.loads(r["steps_json"]):
        print(f"    {s['step_no']:>2} {s['phase'][:5]} {s['operation']:<26} {s['system_id']:<20} "
              f"{s['resource_id']:<18} {s['evidence_id']}")

print("\nRules:")
for r in rd("deletion_rules.csv"):
    print(f"  {r['data_category']:<22} {r['required_action']:<10} {r['condition']}")

act = rd("system_activity.csv")
print("\nActivity event types:", collections.Counter(a["event_type"] for a in act).most_common())
print("Evidence file types:", collections.Counter(f["file_path"].rsplit(".", 1)[1] for f in rd("evidence_files.csv")))