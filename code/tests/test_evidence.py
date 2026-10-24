import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from auditor.evidence import Evidence

EV = Evidence()


def latest(rid):
    return max(EV.by_resource[rid], key=lambda o: o.time)


def test_tombstones_31_vs_32():
    assert latest("tombstone_440").pii is False
    assert latest("tombstone_9178").pii is True


def test_replica_drift_account_005():
    tables = {o.table for o in EV.by_resource["account_005"]}
    assert "customer_profiles_failover_replica" in tables
    assert "customer_profiles_primary" not in tables


def test_handover_and_export():
    assert latest("data_flow_9522").flow_active is True
    assert latest("account_6440").present is False
    assert latest("account_5334").present is True
def test_trace_links_email_to_account():
    o = latest("account_4092")
    assert o.present is False and "e:leonie.g9352@outlook.com" in o.ids


def test_old_hash_contact_lookup_is_secondary_identifier():
    o = latest("analytics_9914")
    assert o.category == "SECONDARY_IDENTIFIER" and o.present


def test_decoy_profile_service_ignored():
    assert "account_55256" not in EV.by_resource


def test_support_replica_copy_still_present():
    assert latest("support_002").present is True