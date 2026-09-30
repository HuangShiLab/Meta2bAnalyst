"""Planner behaviour found wrong in the thesis Chapter 5 evaluation (Table 5.4)."""
import pandas as pd
import pytest

from app.agent.planner import AnalysisPlanner, infer_experimental_design

SESSION = {"session_files": ["Matched_microbes_abd_261.tsv", "Matched_metabolites_abd_261.txt",
                             "Matched_metadata_261.tsv"]}


def _meta():
    rows = []
    for h in range(6):
        for v in ("T1", "T4", "T9"):
            rows.append({"sample": f"H{h}_{v}", "Host_ID": f"H{h}", "Visit": v,
                         "Group": "High" if h < 3 else "Low"})
    return pd.DataFrame(rows).set_index("sample")


async def _plan(query, context=None, use_llm=False):
    return await AnalysisPlanner(use_llm=use_llm).plan(query, dict(context or {}))


def _modules(plan):
    return [s.module for s in plan.steps]


class TestEnrichmentMeansDifferentialAbundance:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", [
        "哪些菌在牙龈炎进展中富集？",
        "which bacteria are enriched in gingivitis?",
        "Which genera are depleted after day 28",
    ])
    async def test_taxon_enrichment_routes_to_markers(self, query):
        plan = await _plan(query, SESSION)
        assert "microbiome_marker" in _modules(plan)
        assert "pathway_kegg" not in _modules(plan)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", ["KEGG pathway enrichment", "做通路富集分析"])
    async def test_pathway_enrichment_still_routes_to_kegg(self, query):
        plan = await _plan(query, SESSION)
        assert "pathway_kegg" in _modules(plan)


class TestNamedUnavailableMethods:
    @pytest.mark.asyncio
    async def test_deseq2_is_not_answered_with_a_generic_pipeline(self):
        plan = await _plan("Run DESeq2 on the genus table", SESSION)
        assert plan.clarification_needed
        assert plan.steps == []
        assert plan.unavailable_methods == ["DESeq2"]
        assert any("DESeq2" in n and "not available" in n for n in plan.notes)
        assert any("ANCOM-BC" in sg["label"] for sg in plan.suggestions)

    @pytest.mark.asyncio
    async def test_flashweave_is_not_silently_replaced_by_sparcc(self):
        plan = await _plan("Estimate a FlashWeave network", SESSION)
        assert plan.clarification_needed
        assert "network_sparcc" not in _modules(plan)
        assert any("FlashWeave" in n for n in plan.notes)

    @pytest.mark.asyncio
    async def test_explicitly_named_alternative_still_runs(self):
        plan = await _plan("Build a SparCC network and a FlashWeave network", SESSION)
        assert not plan.clarification_needed
        assert "network_sparcc" in _modules(plan)
        assert any("FlashWeave" in n and "not substituted" in n for n in plan.notes)

    @pytest.mark.asyncio
    async def test_llm_is_not_asked_to_substitute(self, monkeypatch):
        called = []

        async def boom(self, query, context=None):
            called.append(query)
            return None

        monkeypatch.setattr(AnalysisPlanner, "_llm_plan", boom)
        plan = await _plan("Run DESeq2 on the genus table", SESSION, use_llm=True)
        assert plan.clarification_needed and not called

    @pytest.mark.asyncio
    async def test_suggestions_are_plannable(self):
        plan = await _plan("Run DESeq2 please", SESSION)
        for sg in plan.suggestions:
            follow = await _plan(sg["query"], SESSION)
            assert not follow.clarification_needed, sg


class TestNoAnalyticalContent:
    @pytest.mark.asyncio
    async def test_vague_request_asks_instead_of_running_a_default_pipeline(self):
        plan = await _plan("make it look nice", SESSION)
        assert plan.clarification_needed
        assert plan.steps == []

    @pytest.mark.asyncio
    async def test_open_request_still_gets_the_data_driven_pipeline(self):
        plan = await _plan("analyze my data", SESSION)
        assert not plan.clarification_needed
        assert len(plan.steps) > 1


class TestRepeatedMeasuresDesign:
    def test_detects_participants_and_visits_from_real_column_names(self):
        design = infer_experimental_design(_meta())
        assert design["subject_column"] == "Host_ID"
        assert design["time_column"] == "Visit"
        assert design["longitudinal"] is True

    @pytest.mark.asyncio
    async def test_permanova_gets_subject_column(self):
        ctx = dict(SESSION, metadata=_meta())
        plan = await _plan("Run Bray-Curtis PCoA and test it with PERMANOVA", ctx)
        perm = next(s for s in plan.steps if s.module == "permanova")
        assert perm.params.get("subject_column") == "Host_ID"
        assert any("Repeated measures" in n for n in plan.notes)

    @pytest.mark.asyncio
    async def test_demo_defaults_not_forced_on_other_datasets(self):
        meta = _meta().rename(columns={"Visit": "Timepoint"})
        meta["Timepoint"] = meta["Timepoint"].map({"T1": "D-21", "T4": "D0", "T9": "D28"})
        ctx = dict(SESSION, metadata=meta)
        plan = await _plan("find differential markers comparing timepoints", ctx)
        mk = next(s for s in plan.steps if s.module == "microbiome_marker")
        assert mk.params.get("group_column") == "Timepoint"
        assert mk.params.get("reference_group") != "T4"


class TestDesignRulesDoNotFabricateRequests:
    @pytest.mark.asyncio
    async def test_vague_request_with_metadata_still_asks(self):
        ctx = dict(SESSION, metadata=_meta())
        plan = await _plan("make it look nice", ctx)
        assert plan.clarification_needed
        assert plan.steps == []

    @pytest.mark.asyncio
    async def test_no_unused_normalization_step_without_batch_correction(self):
        ctx = dict(SESSION, metadata=_meta())
        plan = await _plan("Run Bray-Curtis PCoA and test it with PERMANOVA", ctx)
        assert "normalization" not in _modules(plan)
