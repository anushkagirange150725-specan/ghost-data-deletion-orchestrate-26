import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from auditor.data import load
from auditor.intent import wants_deletion

CASES = load("sample_deletion_requests.csv") + load("deletion_requests.csv")
TRUTH = {r["case_id"]: r["deletion_status"] for r in load("sample_output.csv")}
KEEPS = {"keeps the account", "refuses deletion", "removes one field only", "says it is not a deletion request"}


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?。？])\s*", text) if s.strip()]


def test_samples_match_the_answer_key():
    wrong = [c["case_id"] for c in CASES if c["case_id"] in TRUTH
             and wants_deletion(c["request_text"])[0] != (TRUTH[c["case_id"]] != "NOT_APPLICABLE")]
    assert wrong == []


def test_every_request_is_decided_by_its_own_words():
    fallback = [c["case_id"] for c in CASES if wants_deletion(c["request_text"])[1] == "no deletion wording"]
    assert fallback == []


def test_no_request_both_asks_and_keeps():
    mixed = []
    for c in CASES:
        verdicts = {wants_deletion(s)[1].split(":")[0] for s in sentences(c["request_text"])}
        if "asks for deletion" in verdicts and verdicts & KEEPS:
            mixed.append(c["case_id"])
    assert mixed == []


@pytest.mark.parametrize("text, wanted", [
    ("Please delete my account.", True),
    ("Solicito la eliminación permanente de la cuenta.", True),
    ("アカウントの完全な削除を依頼します。", True),
    ("Do not close the account.", False),
    ("Por favor, no borren mi cuenta.", False),
    ("Ne supprimez pas mon compte.", False),
    ("アカウントを削除しないでください。", False),
])
def test_negation_in_several_languages(text, wanted):
    assert wants_deletion(text)[0] == wanted