"""Tests for the rule-based Agent planner.

Guards the two failure modes this module had:
1. ordinary phrasings collapsed to a single data_validator step, and
2. plans referencing modules that are not in MODULE_REGISTRY (and therefore
   cannot be executed).
"""
import copy

import pytest

from app.agent.module_registry import MODULE_REGISTRY
from app.agent.planner import (
    ANALYSIS_TEMPLATES,
    MODULE_KEYWORDS,
    get_planner,
    unregistered_keyword_modules,
)


async def _plan(query, context=None):
    return await get_planner().plan(query, context)


def _modules(plan):
    return [s.module for s in plan.steps]


class TestOrdinaryPhrasings:
    """Every-day requests must yield a real, multi-step plan."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query,expected",
        [
            ("find differential markers comparing visits", {"microbiome_marker"}),
            ("run PCoA and PERMANOVA on the microbiome", {"microbiome_pcoa", "permanova"}),
            ("correlate genera with metabolites", {"cross_correlation"}),
            ("差异标记物分析", {"microbiome_marker", "metabolome_marker"}),
        ],
    )
    async def test_multi_step_plan_with_expected_modules(self, query, expected):
        plan = await _plan(query)
        modules = set(_modules(plan))

        assert not plan.clarification_needed, f"{query!r} was not understood: {plan.notes}"
        assert len(plan.steps) > 1, f"{query!r} planned {len(plan.steps)} step(s): {plan.notes}"
        assert expected <= modules, f"{query!r} planned {sorted(modules)}, missing {sorted(expected - modules)}"
        assert plan.steps[0].module == "data_validator"

    @pytest.mark.asyncio
    async def test_marker_query_uses_compositional_defaults(self):
        plan = await _plan("find differential markers comparing visits")
        mb = next(s for s in plan.steps if s.module == "microbiome_marker")
        assert mb.params["transformation"] == "clr"
        assert mb.params["test_method"] == "mannwhitney"

    @pytest.mark.asyncio
    async def test_template_does_not_swallow_other_requested_modules(self):
        plan = await _plan("run PCoA and find differential markers")
        modules = set(_modules(plan))
        assert {"microbiome_marker", "microbiome_pcoa"} <= modules


class TestPlanIsRunnable:
    """Nothing a plan contains may be absent from the module registry."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "find differential markers comparing visits",
            "run PCoA and PERMANOVA on the microbiome",
            "correlate genera with metabolites",
            "差异标记物分析",
            "does treatment affect the microbiome?",          # template references anosim
            "which taxa are associated with disease?",        # template references random_forest/volcano
            "run the full multi-omics pipeline and generate a report",
            "analyze my data for me",
            "how does the microbiome change over time?",
        ],
    )
    async def test_all_planned_modules_are_registered(self, query):
        plan = await _plan(query)
        unknown = [m for m in _modules(plan) if m not in MODULE_REGISTRY]
        assert not unknown, f"{query!r} planned unregistered modules: {unknown}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "does treatment affect the microbiome?",
            "which taxa are associated with disease?",
            "run the full multi-omics pipeline and generate a report",
        ],
    )
    async def test_no_dangling_dependencies(self, query):
        plan = await _plan(query)
        ids = {s.id for s in plan.steps}
        for step in plan.steps:
            missing = [d for d in step.depends_on if d not in ids]
            assert not missing, f"{step.id} depends on missing step(s) {missing}"

    @pytest.mark.asyncio
    async def test_report_runs_after_the_analyses_it_summarises(self):
        plan = await _plan("run the full multi-omics pipeline and generate a report")
        report = next((s for s in plan.steps if s.module == "report_generator"), None)
        assert report is not None
        analysis_ids = [s.id for s in plan.steps
                        if s.module not in ("data_validator", "report_generator")]
        assert set(analysis_ids) <= set(report.depends_on)


class TestUnmatchedQueries:
    """An unrecognised query must say so instead of faking a 1-step plan."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", ["what is the weather in paris", "qqq zzz nonsense"])
    async def test_clarification_instead_of_validator_only_plan(self, query):
        plan = await _plan(query)
        assert plan.clarification_needed
        assert plan.steps == []
        assert any("CLARIFICATION NEEDED" in n for n in plan.notes)

    @pytest.mark.asyncio
    async def test_wired_keyword_module_is_plannable(self):
        """wgcna now has BOTH a ModuleSpec and an executor function."""
        plan = await _plan("run wgcna on my data")
        assert not plan.clarification_needed
        assert "wgcna" in _modules(plan)

    @pytest.mark.asyncio
    async def test_unavailable_module_is_named(self, monkeypatch):
        """A keyword-routable module with no registry entry is named, not planned."""
        from app.agent import planner as planner_mod
        monkeypatch.delitem(planner_mod.MODULE_REGISTRY, "wgcna")
        plan = await _plan("run wgcna on my data")
        assert plan.clarification_needed
        assert any("wgcna" in n for n in plan.notes)

    @pytest.mark.asyncio
    async def test_unavailable_module_is_reported_alongside_a_real_plan(self, monkeypatch):
        from app.agent import planner as planner_mod
        monkeypatch.delitem(planner_mod.MODULE_REGISTRY, "wgcna")
        plan = await _plan("run wgcna and pcoa")
        assert not plan.clarification_needed
        assert "microbiome_pcoa" in _modules(plan)
        assert any("wgcna" in n and "not available" in n for n in plan.notes)

    @pytest.mark.asyncio
    async def test_plot_view_of_a_planned_module_is_not_called_unavailable(self):
        """Marker modules already emit volcano plots - do not warn about them."""
        plan = await _plan("volcano plot of differential taxa")
        assert "microbiome_marker" in _modules(plan)
        assert not any("not available" in n and "volcano" in n for n in plan.notes)


class TestRegistryDrift:
    """Keyword routing may name more modules than are registered, but a plan
    never may - unregistered names are reported, not scheduled."""

    def test_unregistered_keywords_are_reported_not_planned(self):
        pending = unregistered_keyword_modules()
        assert set(pending).isdisjoint(MODULE_REGISTRY)
        assert set(pending) <= set(MODULE_KEYWORDS)

    def test_every_registered_module_keeps_a_spec(self):
        for name, spec in MODULE_REGISTRY.items():
            assert spec.name == name
            assert spec.category
            assert spec.description
            assert isinstance(spec.input_requirements, dict)

    def test_templates_are_still_declared_for_pending_modules(self):
        """Template steps may name pending modules; the planner filters them."""
        template_modules = {s["module"] for t in ANALYSIS_TEMPLATES for s in t["steps"]}
        assert template_modules, "templates lost their steps"

    @pytest.mark.asyncio
    async def test_planning_does_not_mutate_the_templates(self):
        before = copy.deepcopy(ANALYSIS_TEMPLATES)
        await _plan("run the full multi-omics pipeline")
        await _plan("find differential markers comparing visits")
        assert ANALYSIS_TEMPLATES == before, "planning leaked params into ANALYSIS_TEMPLATES"


class TestSessionAwarePlanning:
    """Session context must scope the plan instead of overriding the query."""

    @pytest.mark.asyncio
    async def test_specific_query_is_not_replaced_by_generic_pipeline(self):
        context = {"session_files": ["feature_table_microbiome.tsv", "metabolome.tsv", "metadata.tsv"]}
        plan = await _plan("correlate genera with metabolites", context)
        assert "cross_correlation" in _modules(plan)

    @pytest.mark.asyncio
    async def test_microbiome_only_session_drops_metabolome_steps(self):
        context = {"session_files": ["feature_table_microbiome.tsv", "metadata.tsv"]}
        plan = await _plan("差异标记物分析", context)
        modules = _modules(plan)
        assert "microbiome_marker" in modules
        assert "metabolome_marker" not in modules

    @pytest.mark.asyncio
    async def test_open_ended_query_uses_uploaded_files(self):
        context = {"session_files": ["metaphlan_profile.tsv", "metadata.tsv"]}
        plan = await _plan("analyze my data", context)
        assert len(plan.steps) > 1
        assert any("metaphlan" in n.lower() for n in plan.notes)
