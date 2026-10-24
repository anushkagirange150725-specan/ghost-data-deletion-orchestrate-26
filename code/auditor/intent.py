from __future__ import annotations
import re
import unicodedata

# Words that ask for removal. Text is lowercased and Latin accents removed first,
# so "löschen" is written "losch", "exclusão" is "exclusao", "données" is "donnees".
DELETE = [
    r"\bdelet", r"\beras(e|ure|ing)", r"\bwipe", r"\bpurge", r"\bforget me\b", r"\bforgotten\b",
    r"\bget rid of\b", r"\bremov", r"\bclos(e|ed|ing) (my|this|the) account", r"\bgone\b",
    r"\bwould like it closed", r"\bdisconnected my account",
    r"\bborr(ar|en|e|a|ado|ada)\b", r"\belimin", r"\bsuprim", r"\bdar de baja\b",          # es / it / pt
    r"\bexclu(a|am|ir|ida|ido|sao)\b", r"\bapag(ar|uem|ue|a)\b", r"\bencerr(ar|em) (a |minha )?conta",
    r"\bsupprim", r"\bsuppression\b", r"\beffac", r"\bclotur",                              # fr
    r"loe?sch", r"entfern",                                                                 # de
    r"\bcancell(are|ate|a)\b", r"\brimuov",                                                 # it
    r"\bverwijder",                                                                         # nl
    r"удал", r"删除", r"注销", r"削除", r"消去", r"退会", r"삭제", r"탈퇴",                    # ru zh ja ko
    r"احذف", r"حذف", r"مسح", r"हटा", r"मिटा", r"डिलीट",                                      # ar hi
]
# Phrases that say the account must stay.
KEEP = [r"\bkeep (the|my|this) account", r"\bleave (the|my) (account|profile)", r"\bcontinue using\b",
        r"\bstill (need|want|use)\b", r"\bkeep the account as it is\b"]
# Phrases that say this is not a deletion request at all.
NOT_REQUEST = [r"\bnot (a |an )?(asking|requesting|request)\b", r"\binformation request\b",
               r"\bbefore deciding\b", r"\b(whether|if) you (will|would|can) (delete|erase)"]
# Negation in the few characters before a verb, or (ja / ko / fr) just after it.
NEG_BEFORE = re.compile(r"(\b(don'?t|do not|does not|never|not|no|nao|nicht|kein\w*|non|niet|sin|sem|"
                        r"sans|without|nolonger)\b|\bne\b|\bне\b|不要|别)[^.]{0,25}$")
NEG_AFTER = re.compile(r"^\w{0,6}\s?(pas\b|しないで|ないで|지 ?마|하지 ?마|하지 않)")
# Removal aimed at one field, not at the account or personal data.
FIELD = r"\b(phone|number|address|newsletter|marketing|mailing|promotional|card|payment|photo|surname|name)\b"
WHOLE = r"\b(account|profile|data|information|details|records|everything|all|conta|cuenta|compte|konto|dados|datos|donnees)\b"
SPLIT = re.compile(r"[.!?;。！？\n]+|\b(?:but|however|pero|mais|mas|aber|ma|maar)\b")


def fold(text: str) -> str:
    """Lowercase, NFKC (full-width -> normal), straight quotes, Latin accents removed."""
    t = unicodedata.normalize("NFKC", text).lower().replace("\u2019", "'").replace("\u2018", "'")
    t = re.sub(r"[\u200b-\u200d\ufeff]", "", t).replace("no longer", "nolonger")
    out = []
    for ch in unicodedata.normalize("NFD", t):
        if unicodedata.category(ch) == "Mn" and out and out[-1].isascii():
            continue                      # drop an accent only when it sits on a Latin letter
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def negated(clause: str, start: int, end: int) -> bool:
    return bool(NEG_BEFORE.search(clause[:start]) or NEG_AFTER.search(clause[end:]))


def wants_deletion(text: str) -> tuple[bool, str]:
    t = fold(text)
    if any(re.search(p, t) for p in NOT_REQUEST):
        return False, "says it is not a deletion request"
    asks, keeps = [], []
    for clause in filter(None, (c.strip() for c in SPLIT.split(t) if c)):
        for p in DELETE:
            m = re.search(p, clause)
            if not m:
                continue
            if negated(clause, m.start(), m.end()):
                keeps.append("refuses deletion: " + clause)
            elif re.search(FIELD, clause) and not re.search(WHOLE, clause.replace("account information", "")):
                keeps.append("removes one field only: " + clause)
            else:
                asks.append(clause)
            break
        for p in KEEP:
            m = re.search(p, clause)
            if m and not negated(clause, m.start(), m.end()):
                keeps.append("keeps the account: " + clause)
    if keeps:
        return False, keeps[0]
    if asks:
        return True, "asks for deletion: " + asks[0]
    return False, "no deletion wording"