import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from auditor.identity import Identity
from auditor.intent import wants_deletion
from auditor.checks import similar

idn = Identity()


def test_lookalike_email_is_not_the_subject():
    assert idn.resolve("smartinez6461@gmail.com") is not None
    assert idn.resolve("smartinez6461.jr@gmail.com") is None
    assert similar("smartinez6461.jr@gmail.com", "smartinez6461@gmail.com")


def test_messy_but_exact_email_still_resolves():
    uid = idn.resolve("amina.elmasri@gmail.com")
    for messy in ("  AMINA.ELMASRI@GMAIL.COM ", "mailto:amina.elmasri@gmail.com",
                  "ａｍｉｎａ.elmasri@gmail.com", "amina.elmasri@gmail.com\u200b"):
        assert idn.resolve(messy) == uid


def test_old_email_is_historical():
    assert idn.match_kind("minjun.kim@gmail.com")[0] == "current"
    kinds = {idn.match_kind(e)[0] for u in idn.held for h in idn.held[u]
             if h.token.startswith("e:") and h.until for e in [h.token[2:]]}
    assert kinds == {"historical"}


@pytest.mark.parametrize("text", [
    "I no longer want to continue using the service, please delete my account.",
    "I don't want to keep my account anymore. Erase everything.",
    "Please wipe all my personal data and forget me.",
    "Ich möchte, dass mein Konto gelöscht wird.",
    "Vorrei cancellare il mio account e tutti i miei dati.",
    "Прошу удалить мой аккаунт.",
    "Quero que minha conta seja excluída.",
    "アカウントを削除してください。",
    "PLEASE DELETE MY ACCOUNT",
])
def test_same_intent_different_words(text):
    assert wants_deletion(text)[0]


@pytest.mark.parametrize("text", [
    "Please delete my old phone number and add the new one, keep the account.",
    "Remove me from the newsletter but do not close my account.",
    "Bitte mein Konto nicht löschen, nur die Adresse ändern.",
    "アカウントを削除しないでください。",
    "Can you tell me whether you will delete my data if I ask? Not a request yet.",
    "Someone opened an account with my email. Do not delete it yet, I need it for a police report.",
])
def test_not_a_deletion(text):
    assert not wants_deletion(text)[0]