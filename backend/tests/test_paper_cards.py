"""Tests for paper knowledge cards (Paper2Agent direction C)."""
from app.services import paper_cards


def test_cards_built_from_real_kb():
    cards = paper_cards.get_paper_cards(force_rebuild=True)
    assert cards, "expected at least one paper card from the bundled KB"
    for pmid, card in cards.items():
        assert card["pmid"] == pmid
        assert card["n_associations"] == len(card["associations"]) > 0
        assert card["diseases"]
        assert isinstance(card["summary"], str) and pmid in card["summary"]


def test_known_pmid_card_contents():
    # PMID 34777313 is cited in taxon_db for Faecalibacterium_prausnitzii /
    # type_1_diabetes (enriched, cohort study).
    card = paper_cards.get_paper_card("34777313")
    assert card is not None
    assert "type_1_diabetes" in card["diseases"]
    assert "2021" in card["years"]
    assert "cohort" in card["study_types"]
    assert "Faecalibacterium_prausnitzii" in card["enriched_taxa"]


def test_unknown_pmid_returns_none():
    assert paper_cards.get_paper_card("00000000") is None


def test_list_view_omits_association_detail():
    listed = paper_cards.list_paper_cards()
    assert listed
    assert all("associations" not in c for c in listed)
    ns = [c["n_associations"] for c in listed]
    assert ns == sorted(ns, reverse=True)
