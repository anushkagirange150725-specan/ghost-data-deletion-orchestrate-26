from __future__ import annotations
import re
from .data import ts
from .documents import document_texts
from .evidence import CATEGORY, EMAIL, Observation, system_of

# OCR turns "data_flow_1121" into "data_flow.1121" or "search 1874": accept . , space or nothing
RID = re.compile(r"\b(account|search|analytics|support|export|data[_ .]?flow|backup|audit[_ .]?record|"
                 r"tombstone|legal[_ .]?hold|marketing|object)[_ .,]?\s?(\d{1,5})\b", re.I)
USER = re.compile(r"\buser[_ .]?(\d{1,4})\b", re.I)
LINK = re.compile(r"linked (\S+) \(([^)]+)\) to (\S+@\S+?) and (user_\d+)|"
                  r"confirmed (\S+) \(([^)]+)\) belongs only to (\S+@\S+?) and (user_\d+)")


def norm_rid(prefix: str, num: str) -> str:
    p = re.sub(r"[ ._]", "", prefix.lower())
    p = {"dataflow": "data_flow", "auditrecord": "audit_record", "legalhold": "legal_hold"}.get(p, p)
    return f"{p}_{num}"


def catalogue_links(activity_rows) -> list[dict]:
    """LINK_RESOURCE_IDENTITY events: a catalogue's claim that a record belongs to someone."""
    out = []
    for r in activity_rows:
        if r["event_type"] != "LINK_RESOURCE_IDENTITY":
            continue
        m = LINK.search(r["details"])
        if not m:
            continue
        rid, label, email, uid = [g for g in m.groups() if g is not None]
        out.append({"t": ts(r["event_time"]), "activity_id": r["activity_id"], "resource_id": rid,
                    "label": label, "email": email.lower(), "user_id": uid})
    return out


# Characters OCR confuses with each other. A misread only swaps characters inside one group.
CONFUSE = ["1lit|!", "0od", "5s", "8b3", "2z", "6bg", "9gq"]


def confusable(a: str, b: str) -> bool:
    """Same length, 1-2 differing characters, each difference a known OCR confusion."""
    if len(a) != len(b) or a == b:
        return False
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    return len(diffs) <= 2 and all(any(x in g and y in g for g in CONFUSE) for x, y in diffs)


class Artefacts:
    def __init__(self, ev, idn, links):
        self.ev, self.idn, self.links = ev, idn, links
        self.known = {t[2:] for t in idn.claims if t.startswith("e:")}
        # e-mails typed in structured evidence (SQL / JSON / logs) are real addresses, never OCR noise
        self.typed = {t[2:] for o in ev.obs for t in o.ids if t.startswith("e:")}
        self.labels = {l["label"].lower(): l["resource_id"] for l in links if l["label"] != l["resource_id"]}
        self.repairs = []
        self.texts = document_texts(ev.files)
        self.facts = {fid: self.read(fid, text) for fid, text in self.texts.items()}

    @staticmethod
    def raw_emails(line: str) -> list[str]:
        line = line.replace(",", ".").replace("@outiook", "@outlook").replace("@gmall", "@gmail")
        return [m.lower().strip(".") for m in EMAIL.findall(line)]

    def classify(self, raw, rid, exact_in_doc, users_in_doc, fid):
        """-> (email, kind); kind is exact | real | repaired | uncertain | foreign."""
        if raw in self.known:
            return raw, "exact"
        if raw in self.typed:
            return raw, "real"                      # exists elsewhere as typed data: not a misread
        cands = [e for e in self.known if confusable(raw, e)]
        if len(cands) != 1:
            return raw, ("uncertain" if cands else "foreign")
        fixed = cands[0]
        corroborated = (fixed in exact_in_doc or self.idn.resolve(fixed) in users_in_doc or
                        any(l["resource_id"] == rid and l["email"] == fixed for l in self.links))
        kind = "repaired" if corroborated else "uncertain"
        self.repairs.append({"file_id": fid, "resource_id": rid or "", "ocr_text": raw,
                             "candidate": fixed, "decision": kind})
        return (fixed, kind) if corroborated else (raw, kind)

    def read(self, fid: str, text: str) -> dict:
        lines = text.splitlines()
        exact = {e for line in lines for e in self.raw_emails(line) if e in self.known}
        users = {"user_" + u for u in USER.findall(text)}
        rows, doc_known, doc_unsure = {}, set(), set()
        for line in lines:
            low = line.lower()
            found = {norm_rid(a, b) for a, b in RID.findall(line)}
            found |= {rid for label, rid in self.labels.items() if label in low}
            found = {rid for rid in found if system_of(rid)}
            for raw in self.raw_emails(line):
                for rid in (found or {None}):
                    e, kind = self.classify(raw, rid, exact, users, fid)
                    if kind in ("exact", "repaired"):
                        doc_known.add(e)
                    elif kind == "uncertain":
                        doc_unsure.add(e)
                    if rid:
                        r = rows.setdefault(rid, {"known": set(), "foreign": set(), "unsure": set(),
                                                  "users": set(), "lines": []})
                        r[{"exact": "known", "repaired": "known", "uncertain": "unsure"}.get(kind, "foreign")].add(e)
            for rid in found:
                r = rows.setdefault(rid, {"known": set(), "foreign": set(), "unsure": set(),
                                          "users": set(), "lines": []})
                r["lines"].append(line)
                r["users"] |= {"user_" + u for u in USER.findall(line)}
        return {"rows": rows, "users": users, "known": doc_known, "unsure": doc_unsure, "text": text.lower()}

    def observations(self) -> list[Observation]:
        out = []
        for fid, f in self.facts.items():
            when = ts(self.ev.files[fid]["captured_at"])
            path = self.ev.files[fid]["file_path"].lower()
            foreign = any(r["foreign"] or r["unsure"] for r in f["rows"].values())
            single = len(f["users"]) <= 1 and len(f["known"]) <= 1 and not foreign and not f["unsure"]
            per_system = {}
            for rid in f["rows"]:
                per_system[system_of(rid)] = per_system.get(system_of(rid), 0) + 1
            for rid, r in f["rows"].items():
                system = system_of(rid)
                ids = {"e:" + e for e in r["known"]} | {"u:" + u for u in r["users"]}
                if single and per_system[system] == 1 and not r["foreign"] and not r["unsure"]:
                    ids |= {"e:" + e for e in f["known"]} | {"u:" + u for u in f["users"]}
                body = " ".join(r["lines"]).lower()
                shows_pii = bool(r["known"] or r["foreign"] or re.search(r"\+\d[\d\s\-]{6,}", body))
                o = Observation(fid, when, when, system, rid, CATEGORY[system], ids=ids, table="artefact")
                if system == "account_service":
                    o.pii, o.present = True, not re.search(r"\b(deleted|not found|404)\b", body)
                elif system == "analytics_platform":
                    o.pii = shows_pii or (single and bool(f["known"]))
                elif system in ("support_platform", "object_storage"):
                    attach = "attachment" in f["text"] or ".pdf" in body or "attachment" in path
                    o.category = "SUPPORT_ATTACHMENT" if attach else "SUPPORT_MESSAGE"
                    o.pii = True if attach else (shows_pii or (single and bool(f["known"])))
                elif system == "integration_service":
                    off = re.search(r"\b(disabled|paused|stopped)\b", body)
                    o.flow_active = not off and bool(re.search(r"continuous|healthy|enabled|deliver", f["text"]))
                elif system == "backup_service":
                    o.restore_allowed = not re.search(r"restore (blocked|denied|disabled)|legal hold|deny", f["text"])
                elif system == "identity_service":
                    o.pii = shows_pii
                else:
                    o.pii = True
                out.append(o)
        return out

    def contradicts(self, rid: str, emails: set, audit) -> bool:
        """True when an artefact (captured by audit_at) shows rid bound to someone else's e-mail."""
        for fid, f in self.facts.items():
            r = f["rows"].get(rid)
            if not r or ts(self.ev.files[fid]["captured_at"]) > audit:
                continue
            # an unsure read, or a near-miss of the subject's own address, is not proof of someone else
            shown = r["known"] | {e for e in r["foreign"] if not any(confusable(e, s) for s in emails)}
            if shown and not (shown & emails):
                return True
        return False