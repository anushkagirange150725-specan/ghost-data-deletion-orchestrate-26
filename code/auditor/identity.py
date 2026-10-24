from __future__ import annotations
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from .data import load, ts


def clean(value: str) -> str:
    """Full-width -> normal, drop invisible characters and spaces at the ends."""
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"[\u200b-\u200d\ufeff]", "", value).strip()


def norm(kind: str, value: str) -> str:
    value = clean(value)
    if kind == "email":
        value = re.sub(r"^mailto:", "", value, flags=re.I).strip("<> ")
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
        self.claims = defaultdict(set)          # token -> every user that ever held it
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
            self.claims[token].add(uid)

    def resolve(self, email: str) -> str | None:
        """Exact match only. A token held by two different users is ambiguous -> None."""
        users = self.claims.get(norm("email", email), set())
        return next(iter(users)) if len(users) == 1 else None

    def match_kind(self, email: str) -> tuple[str, object]:
        """('current'|'historical'|'ambiguous'|'unknown', date the email stopped being used)."""
        token = norm("email", email)
        users = self.claims.get(token, set())
        if len(users) != 1:
            return ("ambiguous" if users else "unknown"), None
        until = [h.until for h in self.held[next(iter(users))] if h.token == token]
        return ("current", None) if None in until else ("historical", max(until))

    def tokens(self, uid: str) -> set[str]:
        return {h.token for h in self.held[uid]}