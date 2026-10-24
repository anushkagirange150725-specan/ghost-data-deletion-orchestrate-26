from __future__ import annotations
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from .data import load, ts


def norm(kind: str, value: str) -> str:
    value = value.strip()
    if kind == "email":
        return "e:" + value.lower()
    if kind == "phone":
        return "p:" + re.sub(r"\D", "", value)
    if kind == "email_hash":
        return "h:" + value.lower()
    if kind == "user_id":
        return "u:" + value
    return "n:" + value.lower()


@dataclass
class Held:
    token: str
    since: datetime | None
    until: datetime | None


class Identity:
    def __init__(self):
        self.held = defaultdict(list)
        self.owner = {}
        users = load("user_identities.csv")
        history = sorted(load("user_audit_log.csv"), key=lambda r: r["event_time"])
        changed_at = defaultdict(dict)
        for h in history:
            uid, field = h["user_id"], h["field_name"]
            when = ts(h["event_time"])
            self._add(uid, norm(field, h["old_value"]), changed_at[uid].get(field), when)
            changed_at[uid][field] = when
        for u in users:
            uid = u["user_id"]
            self._add(uid, norm("user_id", uid), None, None)
            for field in ("email", "phone", "email_hash"):
                if u[field]:
                    self._add(uid, norm(field, u[field]), changed_at[uid].get(field), None)

    def _add(self, uid, token, since, until):
        self.held[uid].append(Held(token, since, until))
        if not token.startswith("n:"):
            self.owner.setdefault(token, uid)

    def resolve(self, email: str) -> str | None:
        return self.owner.get(norm("email", email))

    def tokens(self, uid: str) -> set[str]:
        return {h.token for h in self.held[uid]}