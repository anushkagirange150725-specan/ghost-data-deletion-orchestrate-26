from __future__ import annotations
from collections import Counter
from datetime import timedelta
from .activity import Activity, is_policy
from .artefacts import Artefacts, catalogue_links
from .data import ts
from .evidence import CATEGORY, Evidence, system_of
from .identity import Identity
from .intent import wants_deletion
from .policy import build

RETAINED = {"SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"}


class Auditor:
    def __init__(self):
        self.ev = Evidence()
        self.idn = Identity()
        self.act = Activity()
        self.links = catalogue_links(self.act.rows)
        self.art = Artefacts(self.ev, self.idn, self.links)
        for o in self.art.observations():
            self.ev.obs.append(o)
            self.ev.by_resource[o.resource_id].append(o)
        self.by_token = {}
        for o in self.ev.obs:
            for t in o.ids:
                self.by_token.setdefault(t, []).append(o)
        self._users = {}

    def users_of(self, rid):
        if rid not in self._users:
            self._users[rid] = {self.idn.owner[t] for o in self.ev.by_resource.get(rid, [])
                                for t in o.ids if t in self.idn.owner}
        return self._users[rid]

    def linked(self, c):
        uid, audit = c["user_id"], ts(c["audit_at"])
        window = ts(c["requested_at"]) - timedelta(days=7)
        rids = set()
        for t in self.idn.tokens(uid):
            for o in self.by_token.get(t, []):
                if o.table == "artefact" and o.file_time < window:
                    continue
                if o.file_time <= audit:
                    rids.add(o.resource_id)
                elif o.category in RETAINED and o.file_time <= audit + timedelta(days=7):
                    rids.add(o.resource_id)
        emails = {t[2:] for t in self.idn.tokens(uid) if t.startswith("e:")}
        for l in self.links:
            if window <= l["t"] <= audit and (l["user_id"] == uid or l["email"] in emails):
                if not self.art.contradicts(l["resource_id"], emails, audit):
                    rids.add(l["resource_id"])
        return rids

    def prepare(self, cases):
        self.cases = []
        for c in cases:
            c = dict(c)
            c["user_id"] = self.idn.resolve(c["email"])
            # no known subject -> nobody's data can be authorised for deletion
            c["deletion"] = c["user_id"] is not None and wants_deletion(c["request_text"])[0]
            self.cases.append(c)
        self.cases_all = self.cases
        self.cases = [c for c in self.cases_all if c["deletion"]]
        linked = {c["case_id"]: self.linked(c) for c in self.cases}
        owner = {}
        for cid, rids in linked.items():
            for r in rids:
                owner.setdefault(r, set()).add(cid)
        free = [e for e in self.act.followups if not owner.get(e["resource_id"]) and not self.users_of(e["resource_id"])]
        free_policy = [e for e in free if is_policy(e)]
        self.anchors = self.act.assign(self.cases, linked, self.users_of, free_policy)
        extra = self.act.attach(self.anchors, linked, {c["case_id"]: c for c in self.cases}, free)
        self.linked_by_case = {cid: rids | extra.get(cid, set()) for cid, rids in linked.items()}



    def state(self, rid, audit):
        every = self.ev.by_resource.get(rid, [])
        usable = [o for o in every if o.file_time <= audit and o.time <= audit]
        cats = [o.category for o in (usable or every)]
        if cats:
            category = next((c for c in ("SECONDARY_IDENTIFIER", "SUPPORT_ATTACHMENT") if c in cats), cats[-1])
        else:
            category = CATEGORY.get(system_of(rid), "USER_PROFILE")
        res = {"system": system_of(rid), "resource_id": rid, "category": category,
               "present": category in RETAINED, "pii": False, "flow_active": None,
               "restore_allowed": None, "evidence": ""}
        if usable:
            newest = max(o.time for o in usable)
            latest = [o for o in usable if o.time == newest]
            alive = [o for o in latest if o.present]
            res["present"] = bool(alive)
            res["pii"] = any(o.pii for o in alive)
            res["flow_active"] = any(o.flow_active for o in latest if o.flow_active is not None)
            res["restore_allowed"] = any(o.restore_allowed for o in latest if o.restore_allowed is not None)
            res["evidence"] = (alive or latest)[0].file_id
        elif category not in RETAINED:
            scopes = [s for s in self.ev.scopes if s[3] == res["system"] and s[1] <= audit and s[2] <= audit]
            if scopes:
                res["evidence"] = max(scopes, key=lambda s: (s[1], s[0]))[0]
        return res

    def audit(self, case):
        c = next(x for x in self.cases_all if x["case_id"] == case["case_id"])
        if not c["deletion"]:
            return "NOT_APPLICABLE", []
        audit = ts(c["audit_at"])
        rids = set(self.linked_by_case[c["case_id"]])
        anchor = self.anchors.get(c["case_id"])
        accounts = [r for r in rids if r.startswith("account_")]
        if anchor:
            rids = {r for r in rids if not r.startswith("account_")} | {anchor["resource_id"]}
        elif len(accounts) > 1:
            newest = max(accounts, key=lambda r: max(o.time for o in self.ev.by_resource[r]))
            rids = {r for r in rids if not r.startswith("account_")} | {newest}
        resources = [self.state(r, audit) for r in sorted(rids)]
        main = Counter(r["evidence"] for r in resources if r["evidence"]).most_common(1)
        for r in resources:
            if not r["evidence"] and main:
                r["evidence"] = main[0][0]
        return build(resources)