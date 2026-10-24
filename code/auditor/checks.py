from __future__ import annotations
import re
from collections import defaultdict
from difflib import SequenceMatcher
from .intent import wants_deletion


def language(text: str) -> str:
    """Rough language tag, used only for reporting."""
    for tag, rx in (("ja", r"[\u3040-\u30ff]"), ("ko", r"[\uac00-\ud7af]"), ("zh", r"[\u4e00-\u9fff]"),
                    ("ru", r"[\u0400-\u04ff]"), ("ar", r"[\u0600-\u06ff]"), ("hi", r"[\u0900-\u097f]")):
        if re.search(rx, text):
            return tag
    t = text.lower()
    for tag, rx in (("pt", r"\b(minha|meus|você|não|conta)\b"), ("es", r"\b(mi|mis|cuenta|datos)\b"),
                    ("fr", r"\b(mon|mes|compte|données)\b"), ("de", r"\b(mein|konto|bitte)\b"),
                    ("it", r"\b(il mio|account e|vorrei)\b")):
        if re.search(rx, t):
            return tag
    return "en"


def skeleton(email: str) -> str:
    """Local part without dots, digits, '_', '-' or a '.jr' suffix: catches look-alikes."""
    local, _, domain = email.lower().partition("@")
    return re.sub(r"[._\-\d]", "", re.sub(r"\.?jr$", "", local)) + "@" + domain


def similar(a: str, b: str) -> bool:
    return a != b and (skeleton(a) == skeleton(b) or SequenceMatcher(None, a, b).ratio() >= 0.88)


def subject_checks(auditor) -> list[dict]:
    idn = auditor.idn
    unowned = defaultdict(set)                      # evidence e-mails that belong to nobody
    for o in auditor.ev.obs:
        for t in o.ids:
            if t.startswith("e:") and t not in idn.claims:
                unowned[t[2:]].add(o.resource_id)
    per_user = defaultdict(list)
    for c in auditor.cases_all:
        per_user[c["user_id"]].append(c["case_id"])
    rows = []
    for c in auditor.cases_all:
        flags = []
        kind, until = idn.match_kind(c["email"])
        if kind == "historical":
            flags.append(f"HISTORICAL_EMAIL replaced {until:%Y-%m-%d}")
        elif kind != "current":
            flags.append(f"IDENTITY_{kind.upper()}")
        own = {t[2:] for t in idn.tokens(c["user_id"]) if t.startswith("e:")} if c["user_id"] else set()
        for e, rids in sorted(unowned.items()):
            if any(similar(e, mine) for mine in own):
                flags.append(f"LOOKALIKE_IGNORED {e} in {','.join(sorted(rids))}")
        others = [x for x in per_user[c["user_id"]] if x != c["case_id"]] if c["user_id"] else []
        if others:
            flags.append("REPEAT_REQUEST also " + ",".join(others))
        if c["deletion"] and not auditor.linked_by_case.get(c["case_id"]):
            flags.append("NO_EVIDENCE_FOUND")
        rows.append({"case_id": c["case_id"], "language": language(c["request_text"]),
                     "match": kind, "intent": wants_deletion(c["request_text"])[1][:120],
                     "flags": " | ".join(flags)})
    return rows