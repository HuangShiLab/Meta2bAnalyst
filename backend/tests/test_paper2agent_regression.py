"""Paper2Agent regression: raw LLM plans from three landmark multi-omics
papers must keep executing on a Huang-style dataset.

Fixtures under fixtures/paper_plans/ are the *unmodified* LLM outputs of
/agent/plan-from-paper for:

- huang2021_mbio.json        Huang et al. 2021 mBio (the sample-data paper)
- lloydprice2019_ibd.json    Lloyd-Price et al. 2019 Nature (IBDMDB)
- zhou2019_prediabetes.json  Zhou et al. 2019 Nature (prediabetes)

Their parameters deliberately speak each paper's vocabulary (``distance``,
``reference``, ``timepoint``, ``diagnosis``, ``insulin_resistance``), so any
regression in the executor's parameter normalization layer (alias mapping,
column snapping, reference-level defaulting, data-layer routing) fails here.

LLM calls are not made; the plans are replayed verbatim. Execution is real.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.agent.executor import WorkflowExecutor
from app.agent.planner import ExecutionPlan, PlanStep

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "paper_plans"


def _load_plan(name: str) -> ExecutionPlan:
    data = json.loads((FIXTURE_DIR / f"{name}.json").read_text())
    steps = [
        PlanStep(
            id=s["id"],
            module=s["module"],
            params=s.get("params") or {},
            depends_on=s.get("depends_on") or [],
            description=s.get("description") or "",
        )
        for s in data["steps"]
    ]
    return ExecutionPlan(query=data["paper"], steps=steps, estimated_time="")


@pytest.fixture
def huang_like_data():
    """Synthetic data with the Huang 2021 metadata column names, so the paper
    plans' columns (timepoint/bleeding/subject/diagnosis) have snapping
    targets: Timepoint(DAY0/DAY14), Bleeding, Host_ID, Group(High/Low_bleeder).
    """
    rng = np.random.default_rng(42)
    samples = [f"S{i}" for i in range(24)]
    microbiome_df = pd.DataFrame(
        rng.poisson(10, (40, 24)).astype(float),
        index=[f"g__Genus{i}" for i in range(40)],
        columns=samples,
    )
    metabolome_df = pd.DataFrame(
        rng.lognormal(5, 1, (50, 24)),
        index=[f"Met{i}" for i in range(50)],
        columns=samples,
    )
    metadata_df = pd.DataFrame(
        {
            "Timepoint": ["DAY0"] * 12 + ["DAY14"] * 12,
            "Bleeding": ["High", "Low"] * 12,
            "Host_ID": [f"H{i % 12}" for i in range(24)],
            "Group": ["High_bleeder"] * 12 + ["Low_bleeder"] * 12,
        },
        index=samples,
    )
    return microbiome_df, metabolome_df, metadata_df


async def _run(plan_name, data, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    mb, met, md = data
    executor = WorkflowExecutor(session_id="paper2agent-regression")
    executor.set_session_data(mb, met, md)

    by_step = {}   # step_id -> last event dict
    finals = []
    async for ev in executor.execute(_load_plan(plan_name)):
        d = ev.to_dict()
        if ev.step_id:
            by_step[ev.step_id] = d
        if ev.event_type == "complete":
            finals.append(d)
    return executor, by_step, finals


def _corrections(by_step, step_id):
    return (by_step.get(step_id, {}).get("payload") or {}).get("param_corrections") or []


def _correction_kinds(by_step, step_id):
    return {(c["parameter"], c["kind"], c["to"]) for c in _corrections(by_step, step_id)}


class TestHuang2021Plan:
    """The sample-data paper: the full 11-step plan must run clean."""

    @pytest.mark.asyncio
    async def test_full_plan_completes(self, huang_like_data, tmp_path, monkeypatch):
        executor, by_step, finals = await _run("huang2021_mbio", huang_like_data, tmp_path, monkeypatch)
        assert finals, "workflow must reach the complete event"
        final = finals[0]["payload"]
        errors = {sid: d["payload"].get("error") for sid, d in by_step.items()
                  if d["event_type"] == "step_error"}
        assert not errors, f"steps failed on Huang-like data: {errors}"
        assert final["completed"] == 11 and final["failed"] == 0

    @pytest.mark.asyncio
    async def test_parameter_normalization_is_applied(self, huang_like_data, tmp_path, monkeypatch):
        _, by_step, _ = await _run("huang2021_mbio", huang_like_data, tmp_path, monkeypatch)

        # distance="bray" -> distance_metric="braycurtis"
        pcoa = _correction_kinds(by_step, "step2_microbiome_pcoa")
        assert ("distance_metric", "alias", "bray") in pcoa
        assert ("distance_metric", "metric_spelling", "braycurtis") in pcoa

        # permanova formula degrades to its first term, stratify -> Host_ID
        permanova = _correction_kinds(by_step, "step4_permanova")
        assert ("subject_column", "synonym", "Host_ID") in permanova
        assert any(k == "formula_first_term" for _, k, _ in permanova)

        # marker reference="Day0" snaps to the real level "DAY0"
        marker = _correction_kinds(by_step, "step6_microbiome_marker")
        assert ("reference_group", "level_snap", "DAY0") in marker

    @pytest.mark.asyncio
    async def test_permanova_produces_real_statistics(self, huang_like_data, tmp_path, monkeypatch):
        executor, _, _ = await _run("huang2021_mbio", huang_like_data, tmp_path, monkeypatch)
        result = executor.get_result("step4_permanova")
        # Regression guard: error dicts must not count as success (was the
        # silent-empty-result bug).
        assert isinstance(result, dict) and "error" not in result
        assert result.get("pseudo_f") is not None and result.get("pvalue") is not None

    @pytest.mark.asyncio
    async def test_html_report_request_degrades_to_real_pdf(self, huang_like_data, tmp_path, monkeypatch):
        executor, _, _ = await _run("huang2021_mbio", huang_like_data, tmp_path, monkeypatch)
        report = executor.get_result("step11_report")
        assert report["status"] == "generated"
        assert report["requested_format"] == "html" and report["format"] == "pdf"
        path = Path(report["report_path"])
        assert path.exists() and path.read_bytes().startswith(b"%PDF")


class TestLloydPrice2019Plan:
    """IBDMDB: exercises diagnosis->Group snapping and metabolome-layer routing."""

    @pytest.mark.asyncio
    async def test_no_abort_and_report_generated(self, huang_like_data, tmp_path, monkeypatch):
        executor, _, finals = await _run("lloydprice2019_ibd", huang_like_data, tmp_path, monkeypatch)
        assert finals, "a failing optional step must not abort the workflow"
        report = executor.get_result("step19_report")
        assert isinstance(report, dict) and report.get("status") == "generated"

    @pytest.mark.asyncio
    async def test_diagnosis_snaps_to_group_not_timepoint(self, huang_like_data, tmp_path, monkeypatch):
        _, by_step, _ = await _run("lloydprice2019_ibd", huang_like_data, tmp_path, monkeypatch)
        pcoa = _correction_kinds(by_step, "step5_pcoa")
        # Synonym priority: the disease-status column wins over Timepoint.
        assert ("group_column", "column_snap", "Group") in pcoa

    @pytest.mark.asyncio
    async def test_metabolome_permanova_uses_metabolome_table(self, huang_like_data, tmp_path, monkeypatch):
        _, by_step, _ = await _run("lloydprice2019_ibd", huang_like_data, tmp_path, monkeypatch)
        corr = _correction_kinds(by_step, "step10_permanova_mbx")
        assert ("df", "data_layer", "metabolome") in corr

    @pytest.mark.asyncio
    async def test_maaslin_fixed_effects_list_snapping(self, huang_like_data, tmp_path, monkeypatch):
        _, by_step, _ = await _run("lloydprice2019_ibd", huang_like_data, tmp_path, monkeypatch)
        corr = _correction_kinds(by_step, "step11_maaslin")
        assert ("fixed_effects", "column_snap", "Group") in corr

    @pytest.mark.asyncio
    async def test_marker_reference_defaults_to_baseline_level(self, huang_like_data, tmp_path, monkeypatch):
        _, by_step, _ = await _run("lloydprice2019_ibd", huang_like_data, tmp_path, monkeypatch)
        corr = _correction_kinds(by_step, "step12_mbx_marker")
        assert ("reference_group", "default_reference", "High_bleeder") in corr

    @pytest.mark.asyncio
    async def test_pathway_kegg_receives_a_dataframe(self, huang_like_data, tmp_path, monkeypatch):
        executor, by_step, _ = await _run("lloydprice2019_ibd", huang_like_data, tmp_path, monkeypatch)
        # Registry wiring regression: input_requirements 'features' meant no df
        # was ever passed and the step died with a missing-argument error.
        assert by_step["step15_kegg"]["event_type"] == "step_complete"
        assert isinstance(executor.get_result("step15_kegg"), dict)


class TestZhou2019Plan:
    """Prediabetes: phenotype columns absent from the data must fail honestly."""

    @pytest.mark.asyncio
    async def test_missing_phenotype_column_fails_honestly(self, huang_like_data, tmp_path, monkeypatch):
        _, by_step, finals = await _run("zhou2019_prediabetes", huang_like_data, tmp_path, monkeypatch)
        # insulin_resistance is not in the metadata: error, not silent success.
        marker = by_step["step8_mb_marker"]
        assert marker["event_type"] == "step_error"
        assert "insulin_resistance" in str(marker["payload"].get("error"))
        # ...but the workflow must not abort: the report step still runs.
        assert finals

    @pytest.mark.asyncio
    async def test_cross_omics_step_unaffected_by_grouping_failures(self, huang_like_data, tmp_path, monkeypatch):
        executor, by_step, _ = await _run("zhou2019_prediabetes", huang_like_data, tmp_path, monkeypatch)
        assert by_step["step10_cross_corr"]["event_type"] == "step_complete"
        result = executor.get_result("step10_cross_corr")
        assert result.get("n_pairs_tested") or result.get("statistics") or isinstance(result, dict)


class TestDependencySkipping:
    """A step whose dependency failed is skipped; the report step never is."""

    @pytest.mark.asyncio
    async def test_dependent_step_is_skipped_and_report_still_runs(self, huang_like_data, tmp_path, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
        mb, met, md = huang_like_data
        plan = ExecutionPlan(
            query="skip semantics",
            steps=[
                PlanStep(id="a_marker", module="microbiome_marker",
                         params={"group_column": "nonexistent_column"}),
                PlanStep(id="b_after_failure", module="microbiome_pcoa",
                         depends_on=["a_marker"]),
                PlanStep(id="c_report", module="report_generator",
                         params={"format": "pdf"}, depends_on=["a_marker"]),
            ],
        )
        executor = WorkflowExecutor(session_id="paper2agent-skip-test")
        executor.set_session_data(mb, met, md)
        events = [ev.to_dict() async for ev in executor.execute(plan)]
        by_step = {e["step_id"]: e for e in events if e.get("step_id")}

        assert by_step["a_marker"]["event_type"] == "step_error"
        skipped = by_step["b_after_failure"]
        assert skipped["event_type"] == "step_skipped"
        assert "a_marker" in skipped["payload"]["reason"]
        # report_generator depends on the failed step but must still RUN (it
        # summarizes whatever completed; with zero completed analyses it may
        # honestly fail with "no completed analysis steps", which is fine -
        # what it must never be is skipped).
        assert by_step["c_report"]["event_type"] in ("step_complete", "step_error")
        final = [e for e in events if e["event_type"] == "complete"][0]
        assert final["payload"]["skipped"] == 1
