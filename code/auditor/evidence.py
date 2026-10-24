from __future__ import annotations
import json
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from .data import DATASET, load, ts

PREFIX_SYSTEM = [
    ("account_", "account_service"), ("search_", "search_service"),
    ("analytics_", "analytics_platform"), ("support_", "support_platform"),
    ("export_", "export_service"), ("data_flow_", "integration_service"),
    ("backup_", "backup_service"), ("audit_record_", "security_service"),
    ("tombstone_", "identity_service"), ("legal_hold_", "legal_service"),
    ("marketing_", "marketing_platform"), ("object_", "object_storage"),
]
CATEGORY = {
    "account_service": "USER_PROFILE", "search_service": "SEARCH_INDEX_ENTRY",
    "analytics_platform": "ANALYTICS_PROFILE", "support_platform": "SUPPORT_MESSAGE",
    "export_service": "USER_EXPORT", "integration_service": "DATA_FLOW",
    "backup_service": "BACKUP_ARCHIVE", "security_service": "SECURITY_AUDIT_LOG",
    "identity_service": "ACCOUNT_TOMBSTONE", "legal_service": "LEGAL_HOLD_RECORD",
    "marketing_platform": "MARKETING_PROFILE", "object_storage": "SUPPORT_ATTACHMENT",
}
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
HASH = re.compile(r"\b[0-9a-f]{64}\b")
USER = re.compile(r"\buser_\d+\b")
PHONE = re.compile(r"\+\d[\d\s().\-]{6,}\d")


def system_of(rid: str) -> str | None:
    return next((s for p, s in PREFIX_SYSTEM if rid.startswith(p)), None)


def ids_in(value) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, dict):
        return set().union(*[ids_in(v) for v in value.values()]) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*[ids_in(v) for v in value]) if value else set()
    text = str(value)
    out = {"e:" + m.lower() for m in EMAIL.findall(text)}
    out |= {"h:" + m for m in HASH.findall(text.lower())}
    out |= {"u:" + m for m in USER.findall(text)}
    out |= {"p:" + re.sub(r"\D", "", m) for m in PHONE.findall(text)}
    return out


def real(v) -> bool:
    return v not in (None, "", "null") and str(v).strip().upper() not in ("[REDACTED]", "NO DIRECT IDENTIFIER")


def flag(v) -> bool | None:
    if v in (None, "", "null"):
        return None
    return str(v).strip().lower() in ("1", "true", "yes", "enabled", "allowed")


@dataclass
class Observation:
    file_id: str
    time: datetime
    file_time: datetime
    system: str
    resource_id: str
    category: str
    present: bool = True
    pii: bool | None = None
    flow_active: bool | None = None
    restore_allowed: bool | None = None
    ids: set = field(default_factory=set)
    table: str = ""
    retention_until: datetime | None = None
def from_record(fid, when, ftime, system, collection, rec, table="") -> Observation | None:
    rid = rec.get("resource_id")
    if not rid:
        return None
    system = system or system_of(rid)
    clean = {k: v for k, v in rec.items() if k not in ("metrics", "recent_activity")}
    o = Observation(fid, when, ftime, system, rid, CATEGORY.get(system, "UNKNOWN"),
                    ids=ids_in(clean), table=table)
    coll = (collection or "").lower()
    if system == "analytics_platform":
        o.pii = any(real(rec.get(k)) for k in ("user_id", "customer_reference", "email", "phone", "email_hash"))
    elif system == "support_platform":
        if "attachment" in coll or rec.get("file_name"):
            o.category, o.pii = "SUPPORT_ATTACHMENT", True
        else:
            text_ids = {t for t in ids_in(rec.get("message_text")) if not t.startswith("u:")}
            o.pii = bool(text_ids) or any(real(rec.get(k)) for k in ("requester_name", "requester_email", "requester_phone"))
    elif system == "identity_service":
        o.pii = any(real(rec.get(k)) for k in ("name", "full_name", "email", "phone", "email_hash"))
    elif system == "integration_service":
        o.flow_active = flag(rec.get("enabled"))
    elif system == "backup_service":
        o.restore_allowed = flag(rec.get("restore_allowed"))
    elif system in ("security_service", "legal_service"):
        o.retention_until = ts(rec.get("retention_until") or rec.get("retained_until"))
    else:
        o.pii = True
    return o


RESULTS = {"FOUND": (True, True), "IDENTIFIABLE": (True, True), "NOT_FOUND": (False, False),
           "ANONYMIZED": (True, False), "REDACTED": (True, False), "ACTIVE": (True, True),
           "DISABLED": (True, False), "BLOCKED": (True, False)}


def from_lookup(fid, when, ftime, system, rid, rtype, result, subject) -> Observation:
    result = (result or "").upper()
    present, pii = RESULTS.get(result, (True, True))
    system = system or system_of(rid)
    o = Observation(fid, when, ftime, system, rid, rtype or CATEGORY.get(system, "UNKNOWN"),
                    present=present, pii=pii, ids=ids_in(subject), table="lookup")
    if system == "integration_service":
        o.flow_active = result in ("ACTIVE", "FOUND")
    if system == "backup_service":
        o.restore_allowed = result in ("ACTIVE", "FOUND")
    return o
def parse_sql(fid, path, ftime):
    con = sqlite3.connect(":memory:")
    con.executescript(open(path, encoding="utf-8").read())
    out = []
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    scope = {}
    if "snapshot_scope" in tables:
        scope = {s: ts(t) for s, t in con.execute("select origin_system, captured_at from snapshot_scope")}
    inventory = {"customer_profiles": "account_service", "customer_search_documents": "search_service",
                 "customer_analytics_profiles": "analytics_platform", "support_records": "support_platform",
                 "customer_exports": "export_service", "connector_subscriptions": "integration_service",
                 "backup_restore_entries": "backup_service", "security_audit_records": "security_service"}
    for t in tables:
        cols = [c[1] for c in con.execute(f'pragma table_info("{t}")')]
        rows = [dict(zip(cols, r)) for r in con.execute(f'select * from "{t}"')]
        if "record_json" in cols:
            for r in rows:
                o = from_record(fid, ftime, ftime, r["origin_system"], r["collection_name"],
                                json.loads(r["record_json"]), table=t)
                if o:
                    out.append(o)
        elif t in inventory:
            system = inventory[t]
            when = scope.get(system, ftime)
            for r in rows:
                if system == "analytics_platform":
                    r["user_id"] = r.pop("customer_reference", None)
                o = from_record(fid, when, ftime, system, t, r, table="inventory")
                if o:
                    out.append(o)
        elif t.startswith("customer_profiles_") or t.startswith("search_documents_"):
            system = "account_service" if t.startswith("customer_profiles_") else "search_service"
            for r in rows:
                o = from_record(fid, ftime, ftime, system, t, r, table=t)
                if o:
                    out.append(o)
    return out


def parse_json(fid, path, ftime):
    d = json.load(open(path, encoding="utf-8"))
    out = []
    if "snapshots" in d:
        for snap in d["snapshots"]:
            when = ts(snap.get("captured_at")) or ftime
            for rec in snap["records"]:
                if "lookup_value" in rec:
                    out.append(from_lookup(fid, ts(rec["recorded_at"]) or when, ftime, rec["system"],
                                           rec["resource_id"], rec["record_type"], rec["result"], rec["lookup_value"]))
                else:
                    o = from_record(fid, when, ftime, snap["data_store"], snap["collection"], rec, "snapshot")
                    if o:
                        out.append(o)
    elif "service_exports" in d:
        for system, colls in d["service_exports"].items():
            for coll, recs in colls.items():
                for rec in recs:
                    when = ts(rec.get("observed_at")) or ftime
                    rec = dict(rec)
                    if system == "account_service":
                        present = rec.get("status_code") == 200
                        rec = {**(rec.get("profile") or {}), "resource_id": rec["resource_id"]}
                    elif system == "search_service":
                        docs = (rec.get("hits") or {}).get("documents") or []
                        present = bool(docs)
                        rec = {"resource_id": rec["resource_id"], "query": rec.get("query"), "doc": docs}
                    else:
                        present = True
                        if system == "analytics_platform":
                            rec["user_id"] = rec.pop("customer_reference", None)
                    o = from_record(fid, when, ftime, system, coll, rec, "export")
                    o.present = present
                    out.append(o)
    elif d.get("records") and "record_type" in d["records"][0]:
        for rec in d["records"]:
            out.append(from_lookup(fid, ts(rec["recorded_at"]) or ftime, ftime, rec["system"],
                                   rec["resource_id"], rec["record_type"], rec["result"], rec["subject_reference"]))
    elif "records" in d:
        when = ts(d.get("captured_at")) or ftime
        for rec in d["records"]:
            o = from_record(fid, when, ftime, None, d.get("collection"), rec, "snapshot")
            if o:
                out.append(o)
    return out


HANDOVER = re.compile(r"^-\s*(\S+Z)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(.*)$")


def parse_text(fid, path, ftime):
    out = []
    for line in open(path, encoding="utf-8"):
        m = HANDOVER.match(line.strip())
        if m:
            t, system, rid, rtype, result, subject = m.groups()
            out.append(from_lookup(fid, ts(t), ftime, system, rid, rtype, result, subject))
    return out

def scopes_of(path, ftime):
    """(system, time) pairs for full-store captures: a record missing from one is absent then."""
    ext = os.path.splitext(path)[1].lower()
    out = []
    if ext == ".sql":
        con = sqlite3.connect(":memory:")
        con.executescript(open(path, encoding="utf-8").read())
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        if "snapshot_scope" in tables:
            out += [(s, ts(t)) for s, t in con.execute("select origin_system, captured_at from snapshot_scope")]
        if any(t.startswith("customer_profiles_") for t in tables):
            out.append(("account_service", ftime))
        if any(t.startswith("customer_data_") for t in tables):
            out += [(s, ftime) for s in CATEGORY]
    elif ext == ".json":
        d = json.load(open(path, encoding="utf-8"))
        for snap in d.get("snapshots", []):
            if snap.get("collection") != "operational_record_history":
                out.append((snap["data_store"], ts(snap["captured_at"]) or ftime))
    return out

class Evidence:
    def __init__(self):
        self.files = {r["file_id"]: r for r in load("evidence_files.csv")}
        self.obs: list[Observation] = []
        self.scopes = []
        for fid, meta in self.files.items():
            path = os.path.join(DATASET, meta["file_path"])
            ftime = ts(meta["captured_at"])
            ext = os.path.splitext(path)[1].lower()
            from .logs import parse_log
            parser = {".sql": parse_sql, ".json": parse_json, ".txt": parse_text, ".log": parse_log}.get(ext)
            for system, when in scopes_of(path, ftime):
                self.scopes.append((fid, min(when, ftime), ftime, system))
            if parser:
                for o in parser(fid, path, ftime):
                    o.time = min(o.time, ftime)
                    self.obs.append(o)
        self.by_resource = defaultdict(list)
        for o in self.obs:
            self.by_resource[o.resource_id].append(o) 