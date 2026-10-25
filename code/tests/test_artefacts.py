import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from auditor.engine import Auditor

A = Auditor()
ROWS = {}
for fid, f in A.art.facts.items():
    for rid, r in f["rows"].items():
        ROWS.setdefault(rid, {"known": set(), "foreign": set()})
        ROWS[rid]["known"] |= r["known"]
        ROWS[rid]["foreign"] |= r["foreign"]


def test_every_artefact_has_text():
    empty = [fid for fid, text in A.art.texts.items() if len(text.strip()) < 50]
    assert len(A.art.texts) == 15 and empty == []


@pytest.mark.parametrize("rid", ["export_1842", "support_001", "data_flow_1121", "backup_9287",
                                 "search_428", "analytics_7438", "audit_record_003", "marketing_001"])
def test_records_are_found_in_artefacts(rid):
    assert rid in ROWS


def test_ocr_email_is_repaired():
    # the backup console prints "areedt433@gmail.com" for areed1433@gmail.com
    assert "areed1433@gmail.com" in ROWS["backup_9287"]["known"]


def test_lookalike_is_not_repaired_into_the_subject():
    assert "g.silva76@gmail.com" in ROWS["search_428"]["known"]
    assert all(".jr" not in e for e in ROWS.get("search_1874", {"known": set()})["known"])


def test_screenshot_vetoes_catalogue_link():
    # catalogue says marketing_001 is kwame-mensah@proton.me, the console shows Soo-jin Park
    emails = {"kwame-mensah@proton.me"}
    assert A.art.contradicts("marketing_001", emails, max(l["t"] for l in A.links))
    assert not A.art.contradicts("export_1260", {"ingrid.dahl@outlook.com"}, max(l["t"] for l in A.links))


def test_pdf_attachment_is_a_support_attachment():
    obs = [o for o in A.ev.by_resource["support_001"] if o.table == "artefact"]
    assert obs and all(o.category == "SUPPORT_ATTACHMENT" and o.pii for o in obs)


def test_confusable_only_allows_ocr_style_swaps():
    from auditor.artefacts import confusable
    assert confusable("areedt433@gmail.com", "areed1433@gmail.com")      # t <-> 1
    assert confusable("g.siiva76@gmail.com", "g.silva76@gmail.com")      # i <-> l
    assert not confusable("anna.k@gmail.com", "anne.k@gmail.com")        # a <-> e is not an OCR slip
    assert not confusable("g.silva76.jr@gmail.com", "g.silva76@gmail.com")  # different length


def test_address_typed_elsewhere_is_never_repaired():
    assert "g.silva76.jr@gmail.com" in A.art.typed
    assert A.art.classify("g.silva76.jr@gmail.com", None, set(), set(), "t")[1] == "real"


def test_repair_needs_corroboration():
    # same misread with no catalogue link, no exact copy and no user id in the document
    assert A.art.classify("areedt433@gmail.com", None, set(), set(), "t") == ("areedt433@gmail.com", "uncertain")


def test_two_possible_owners_is_not_repaired():
    saved = A.art.known
    A.art.known = {"kim1@x.com", "kiml@x.com"}
    try:
        assert A.art.classify("kimi@x.com", None, set(), set(), "t")[1] == "uncertain"
    finally:
        A.art.known = saved


def test_near_miss_of_subject_does_not_veto():
    audit = max(l["t"] for l in A.links)
    assert not A.art.contradicts("backup_9287", {"areed1433@gmail.com"}, audit)