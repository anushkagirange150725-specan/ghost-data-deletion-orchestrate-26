from __future__ import annotations
from collections import defaultdict
from datetime import timedelta
from .data import load, ts

STATUS_RESULT = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}


def is_policy(e) -> bool:
    return e["details"].startswith("Policy action completed")


def offset(anchor, event) -> int:
    return int((event["t"] - anchor["t"]).total_seconds())


def in_phase(anchor, event) -> bool:
    d = offset(anchor, event)
    if is_policy(event):
        return 15 * 60 <= d <= 75 * 60 and d % 30 in (9, 10, 11)
    return 75 * 60 <= d <= 210 * 60 and d % 30 in (20, 21, 22)

def first_slot(anchor, event) -> bool:
    d = offset(anchor, event)
    return is_policy(event) and 18 * 60 <= d <= 52 * 60 and d % 60 in (40, 41)


class Activity:
    def __init__(self):
        self.rows = load("system_activity.csv")
        for r in self.rows:
            r["t"] = ts(r["event_time"])
        worker = [r for r in self.rows if r["source_system"] == "deletion_worker"]
        self.profile_deletes = [r for r in worker if r["event_type"] == "DELETE_RECORD"
                                and r["target_system"] == "account_service"]
        self.followups = [r for r in worker if r["target_system"] != "account_service"]
        self.by_resource = defaultdict(list)
        for r in worker:
            self.by_resource[r["resource_id"]].append(r)

    def anchor_score(self, case, e, linked, owned_by_case, free_policy):
        accounts = {r for r in linked if r.startswith("account_")}
        chain = [x for r in linked if not r.startswith("account_") for x in self.by_resource.get(r, [])]
        score = 100 if e["resource_id"] in accounts else 0
        hits = [x for x in chain if in_phase(e, x)]
        for x in hits:
            exact = offset(e, x) % 30 in ((10, 11) if is_policy(x) else (21, 22))
            score += 10 if exact else 5
        if hits:
            first = min(hits, key=lambda x: x["t"])
            want = (40, 41) if is_policy(first) else \
                (21, 22) if first["reported_result"] == "SUCCESS" and not first["event_type"].startswith("CHECK") else (51, 52)
            score += 3 if offset(e, first) % 60 in want else 0
        elif any(first_slot(e, p) for p in free_policy):
            score += 6
        before = (ts(case["reported_at"]) - e["t"]).total_seconds() / 60
        score += 2 if 40 <= before <= 80 else 1 if -15 <= before <= 40 else 0
        if STATUS_RESULT.get(case["reported_status"]) == e["reported_result"]:
            score += 5
        return score

    def assign(self, cases, linked, owner_of_resource, free_policy):
        import numpy as np
        from scipy.optimize import linear_sum_assignment
        events = self.profile_deletes
        w = np.zeros((len(cases), len(events)))
        for i, c in enumerate(cases):
            lo = ts(c["requested_at"]) - timedelta(hours=1)
            hi = ts(c["reported_at"]) + timedelta(minutes=20)
            for j, e in enumerate(events):
                if not lo <= e["t"] <= hi:
                    continue
                owners = owner_of_resource(e["resource_id"])
                if owners and c["user_id"] not in owners:
                    continue
                w[i, j] = self.anchor_score(c, e, linked[c["case_id"]], owners, free_policy)
        rows, cols = linear_sum_assignment(-w)
        return {cases[i]["case_id"]: events[j] for i, j in zip(rows, cols) if w[i, j] >= 1}

    def attach(self, anchors, linked, cases_by_id, free_events):
        claims = defaultdict(list)
        for cid, a in anchors.items():
            known = [x for r in linked[cid] if not r.startswith("account_")
                     for x in self.by_resource.get(r, []) if in_phase(a, x)]
            result_chain = any(not is_policy(k) for k in known)
            for e in free_events:
                if e["t"] <= a["t"]:
                    continue
                if first_slot(a, e):
                    claims[e["activity_id"]].append((1 if result_chain else 2, cid, e))
                elif in_phase(a, e):
                    steps = (388, 392, 447, 451) if is_policy(e) else (1108, 1112, 1167, 1171)
                    for k in known:
                        gap = abs((e["t"] - k["t"]).total_seconds())
                        if steps[0] <= gap <= steps[1] or steps[2] <= gap <= steps[3]:
                            claims[e["activity_id"]].append((1, cid, e))
                            break
        extra = defaultdict(set)
        for cl in claims.values():
            best = max(s for s, _, _ in cl)
            top = [x for x in cl if x[0] == best]
            if len(top) == 1:
                extra[top[0][1]].add(top[0][2]["resource_id"])
        return extra