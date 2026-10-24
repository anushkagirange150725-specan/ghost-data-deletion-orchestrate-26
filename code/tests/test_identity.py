import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from auditor.identity import Identity
from auditor.data import load

ID = Identity()


def test_every_request_email_resolves():
    for f in ("deletion_requests.csv", "sample_deletion_requests.csv"):
        missing = [r["case_id"] for r in load(f) if ID.resolve(r["email"]) is None]
        assert missing == [], missing


def test_old_and_new_email_same_user():
    assert ID.resolve("noah.f438085@outlook.com") == ID.resolve("noah.f4380@outlook.com") == "user_29"


def test_email_case_insensitive():
    assert ID.resolve("A.EZE08@GMAIL.COM") == "user_541"
    