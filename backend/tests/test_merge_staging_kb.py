"""Tests for scripts/merge_staging_kb.py -- staging -> KB merge safety rules."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import merge_staging_kb as msk  # noqa: E402


def _paper(pmid, associations, study_type="case_control", year="2020"):
    return {
        "pmid": pmid,
        "title": f"Paper {pmid}",
        "year": year,
        "journal": "Test J",
        "study_type": study_type,
        "cohort_size": 50,
        "associations": associations,
    }


def _assoc(taxon, condition, direction, verified=True, rank="species"):
    return {
        "taxon": taxon,
        "taxon_rank": rank,
        "condition": condition,
        "direction": direction,
        "evidence_quote": "some quote",
        "quote_verified": verified,
        "problems": [],
    }


@pytest.fixture
def kb_files(tmp_path):
    taxon_db = tmp_path / "taxon_db.json"
    disease_db = tmp_path / "disease_db.json"
    taxon_db.write_text(json.dumps({
        "Streptococcus_mutans": {
            "gram_stain": "Gram-positive",
            "oxygen": "facultative_anaerobic",
            "main_products": ["lactate"],
            "known_functions": ["acid_production"],
            "disease_associations": {"dental_caries": "enriched"},
            "health_markers": [],
            "notes": "curated",
        },
    }))
    disease_db.write_text(json.dumps({
        "dental_caries": {
            "indicators": [],
            "key_genera": ["Streptococcus"],
            "functional_shift": [],
            "description": "tooth decay",
        },
        "periodontal_disease": {
            "indicators": [],
            "key_genera": [],
            "functional_shift": [],
            "description": "gum disease",
        },
    }))
    return taxon_db, disease_db


@pytest.fixture
def staging(tmp_path):
    d = tmp_path / "staging"
    d.mkdir()
    return d


def _run(staging, kb_files, apply=True, verified_only=True):
    taxon_db, disease_db = kb_files
    rc = msk.merge(staging, apply, verified_only,
                   taxon_db_path=taxon_db, disease_db_path=disease_db)
    return rc, json.loads(taxon_db.read_text()), json.loads(disease_db.read_text())


class TestMergeRules:
    def test_dry_run_writes_nothing(self, staging, kb_files):
        (staging / "PMID1_x.json").write_text(json.dumps(_paper(
            "1", [_assoc("Prevotella intermedia", "periodontitis", "enriched")])))
        before = kb_files[0].read_text()
        rc, taxa, _ = _run(staging, kb_files, apply=False)
        assert rc == 0
        assert kb_files[0].read_text() == before
        assert "prevotella_intermedia" not in taxa

    def test_new_taxon_gets_skeleton(self, staging, kb_files):
        (staging / "PMID1_x.json").write_text(json.dumps(_paper(
            "1", [_assoc("Prevotella intermedia", "periodontitis", "enriched")])))
        _, taxa, diseases = _run(staging, kb_files)
        entry = taxa["prevotella_intermedia"]
        assert entry["auto_generated"] is True
        assert "[CURATE]" in entry["notes"]
        assert entry["disease_associations"]["periodontal_disease"] == "enriched"
        ev = entry["disease_evidence"]["periodontal_disease"][0]
        assert ev["pmid"] == "1" and ev["quote_verified"] is True
        # mirrored into disease_db
        assert "prevotella_intermedia" in diseases["periodontal_disease"]["literature_evidence"]
        assert "Prevotella" in diseases["periodontal_disease"]["key_genera"]

    def test_existing_association_never_overwritten(self, staging, kb_files):
        """KB says S. mutans is enriched in caries; a paper saying depleted
        must not flip it -- the conflict is reported instead."""
        (staging / "PMID2_x.json").write_text(json.dumps(_paper(
            "2", [_assoc("Streptococcus mutans", "dental_caries", "depleted")])))
        _, taxa, _ = _run(staging, kb_files)
        assert taxa["Streptococcus_mutans"]["disease_associations"]["dental_caries"] == "enriched"
        # but the dissenting evidence is still recorded
        evs = taxa["Streptococcus_mutans"]["disease_evidence"]["dental_caries"]
        assert evs[0]["direction"] == "depleted"

    def test_unverified_quotes_excluded_by_default(self, staging, kb_files):
        (staging / "PMID3_x.json").write_text(json.dumps(_paper(
            "3", [_assoc("Gemella morbillorum", "periodontitis", "enriched",
                         verified=False)])))
        _, taxa, _ = _run(staging, kb_files)
        assert "gemella_morbillorum" not in taxa

    def test_unverified_included_with_flag(self, staging, kb_files):
        (staging / "PMID3_x.json").write_text(json.dumps(_paper(
            "3", [_assoc("Gemella morbillorum", "periodontitis", "enriched",
                         verified=False)])))
        _, taxa, _ = _run(staging, kb_files, verified_only=False)
        assert "gemella_morbillorum" in taxa

    def test_direction_conflict_resolves_to_mixed(self, staging, kb_files):
        (staging / "PMID4_x.json").write_text(json.dumps(_paper(
            "4", [_assoc("Rothia mucilaginosa", "periodontitis", "enriched")],
            study_type="cohort")))
        (staging / "PMID5_x.json").write_text(json.dumps(_paper(
            "5", [_assoc("Rothia mucilaginosa", "periodontitis", "depleted")],
            study_type="cohort")))
        _, taxa, _ = _run(staging, kb_files)
        assert taxa["rothia_mucilaginosa"]["disease_associations"]["periodontal_disease"] == "mixed"

    def test_stronger_evidence_wins_over_weak(self, staging, kb_files):
        (staging / "PMID6_x.json").write_text(json.dumps(_paper(
            "6", [_assoc("Rothia aeria", "periodontitis", "depleted")],
            study_type="in_vitro")))
        (staging / "PMID7_x.json").write_text(json.dumps(_paper(
            "7", [_assoc("Rothia aeria", "periodontitis", "enriched")],
            study_type="rct")))
        _, taxa, _ = _run(staging, kb_files)
        assert taxa["rothia_aeria"]["disease_associations"]["periodontal_disease"] == "enriched"

    def test_blocked_conditions_dropped(self, staging, kb_files):
        (staging / "PMID8_x.json").write_text(json.dumps(_paper(
            "8", [_assoc("Streptococcus mutans", "female", "enriched"),
                  _assoc("Streptococcus mutans", "high_sugar_diet", "enriched")])))
        _, taxa, _ = _run(staging, kb_files)
        assoc = taxa["Streptococcus_mutans"]["disease_associations"]
        assert "female" not in assoc and "high_sugar_diet" not in assoc

    def test_condition_alias_mapping(self, staging, kb_files):
        (staging / "PMID9_x.json").write_text(json.dumps(_paper(
            "9", [_assoc("Porphyromonas gingivalis", "chronic periodontitis", "enriched")])))
        _, taxa, _ = _run(staging, kb_files)
        assert "periodontal_disease" in taxa["porphyromonas_gingivalis"]["disease_associations"]

    def test_unknown_condition_not_mirrored_to_disease_db(self, staging, kb_files):
        (staging / "PMID10_x.json").write_text(json.dumps(_paper(
            "10", [_assoc("Rothia dentocariosa", "oral_mucositis", "depleted")])))
        _, taxa, diseases = _run(staging, kb_files)
        assert "oral_mucositis" not in diseases  # not auto-created
        assert taxa["rothia_dentocariosa"]["disease_associations"]["oral_mucositis"] == "depleted"

    def test_rerun_is_idempotent(self, staging, kb_files):
        (staging / "PMID1_x.json").write_text(json.dumps(_paper(
            "1", [_assoc("Prevotella intermedia", "periodontitis", "enriched")])))
        _run(staging, kb_files)
        _, taxa2, _ = _run(staging, kb_files)
        evs = taxa2["prevotella_intermedia"]["disease_evidence"]["periodontal_disease"]
        assert len(evs) == 1, "re-running must not duplicate evidence records"
