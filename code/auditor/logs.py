from __future__ import annotations
import json
import re
from collections import defaultdict
from .data import ts
from .evidence import Observation, CATEGORY, from_lookup, ids_in, real, flag, system_of

SYSTEMS = set(CATEGORY)
KV = re.compile(r'([A-Za-z_]\w*)=("(?:[^"\\]|\\.)*"|\S+)')
FORMATS = [
    ("json", re.compile(r"^(\S+Z) (\{.*\})\s*$")),
    ("syslog", re.compile(r"^(\S+Z) <\d+>\d+ \S+ (\S+) (\S+) - - (.*)$")),
    ("bracket", re.compile(r"^(\S+Z) \[\w+\] \[([\w\-]+)\] \[([^\]]+)\] ([\w\-]+): ?(.*)$")),
    ("pipe", re.compile(r"^(\S+Z) \| \w+ \| (\S+) \| (\S+) \| (\S+) \| ?(.*)$")),
    ("cloud", re.compile(r'^(\S+Z) requestId=(\S+) level=\w+ function=(\S+) message="(.*)"\s*$')),
]
KEY_FIELDS = ("lookup_key", "match_key", "subject_key", "scan_key", "subject_ref", "owner_key")
LINK_FIELDS = KEY_FIELDS + ("correlation_key", "matched_value", "email", "customer_email", "owner_email",
                            "customer_reference", "subject_reference", "requester_email", "requester_phone")


def kv(text: str) -> dict:
    out = {}
    for k, v in KV.findall(text.replace('\\"', '"') if 'message="' not in text else text):
        out[k] = v[1:-1].replace('\\"', '"') if v.startswith('"') and v.endswith('"') else v
    return out


def parse_line(line: str):
    line = line.rstrip("\n")
    for name, rx in FORMATS:
        m = rx.match(line)
        if not m:
            continue
        if name == "json":
            d = {k: (None if v is None else str(v)) for k, v in json.loads(m.group(2)).items()}
            return m.group(1), d.get("service"), d.get("trace_id"), d.get("event"), d
        if name == "syslog":
            d = kv(m.group(4))
            return m.group(1), m.group(2), m.group(3), d.get("event"), d
        if name in ("bracket", "pipe"):
            return m.group(1), m.group(2), m.group(3), m.group(4), kv(m.group(5))
        if name == "cloud":
            d = kv(m.group(4).replace('\\"', '"'))
            return m.group(1), m.group(3), m.group(2), d.get("event"), d
    m = re.match(r"^(\S+Z) (.*)$", line)
    if not m:
        return None
    d = kv(m.group(2))
    return m.group(1), d.get("service"), d.get("trace_id"), d.get("event"), d


def parse_log(fid, path, ftime):
    lines = [p for p in (parse_line(l) for l in open(path, encoding="utf-8")) if p]
    trace_ids = defaultdict(set)
    for _, _, trace, _, d in lines:
        for k in KEY_FIELDS:
            if real(d.get(k)):
                trace_ids[trace] |= ids_in(d[k])
    out = []
    for t, service, trace, event, d in lines:
        when = ts(t) or ftime
        event = (event or "").lower()
        if event == "record_lookup" or {"record_type", "result", "resource_id"} <= d.keys():
            out.append(from_lookup(fid, when, ftime, d.get("system"), d["resource_id"],
                                   d.get("record_type"), d.get("result"), d.get("subject_reference")))
            continue
        rid = d.get("resource_id", "")
        system = "support_platform" if service == "support_replica" else service
        if system not in SYSTEMS or system_of(rid) != system or event.endswith("_started"):
            continue
        ids = set(trace_ids.get(trace, set()))
        for k in LINK_FIELDS:
            if real(d.get(k)):
                ids |= ids_in(d[k])
        absent = (d.get("rows") == "0" or d.get("http_status") == "404" or d.get("result") == "miss"
                  or d.get("available") == "false" or d.get("marker_found") == "true")
        o = Observation(fid, when, ftime, system, rid, CATEGORY[system], present=not absent, ids=ids, table="log")
        if system == "analytics_platform":
            if event == "contact_lookup_completed":
                o.category, o.pii = "SECONDARY_IDENTIFIER", True
            else:
                o.pii = (d.get("direct_identifiers") not in (None, "0")) or any(
                    real(d.get(k)) for k in ("email", "phone", "email_hash", "matched_value", "customer_reference"))
        elif system == "support_platform":
            if "attachment" in event or d.get("file"):
                o.category, o.pii = "SUPPORT_ATTACHMENT", True
            elif service == "support_replica":
                o.category, o.pii = "SECONDARY_IDENTIFIER", True
            else:
                text_ids = {x for x in ids_in(d.get("message_text")) if not x.startswith("u:")}
                o.pii = bool(text_ids) or any(real(d.get(k)) for k in
                                              ("requester_name", "requester_email", "requester_phone", "matched_value"))
        elif system == "integration_service":
            o.flow_active = flag(d.get("enabled"))
        elif system == "backup_service":
            ra = flag(d.get("restore_allowed"))
            if ra is None and "eligible" in d:
                ra = flag(d["eligible"]) and not flag(d.get("deletion_block"))
            if ra is None and "decision" in d:
                ra = d["decision"].lower() not in ("deny", "denied")
            o.restore_allowed = ra
        elif system == "security_service":
            o.retention_until = ts(d.get("retention_until"))
        else:
            o.pii = not absent
        out.append(o)
    return out