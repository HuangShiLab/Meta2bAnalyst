"""Tests for the Agent executor module."""
from pathlib import Path

import pytest
import pandas as pd
import numpy as np

from app.agent.executor import _get_module_function, WorkflowExecutor
from app.agent.module_registry import get_module_names
from app.agent.planner import ExecutionPlan, PlanStep, get_planner


@pytest.fixture
def sample_data():
    """Create small synthetic microbiome/metabolome/metadata dataframes."""
    samples = [f"S{i}" for i in range(10)]
    microbiome_df = pd.DataFrame(
        np.random.poisson(10, (20, 10)),
        index=[f"Genus{i}" for i in range(20)],
        columns=samples,
    )
    metabolome_df = pd.DataFrame(
        np.random.lognormal(5, 1, (30, 10)),
        index=[f"Met{i}" for i in range(30)],
        columns=samples,
    )
    metadata_df = pd.DataFrame(
        {"Visit": ["T4"] * 5 + ["T5"] * 5},
        index=samples,
    )
    return microbiome_df, metabolome_df, metadata_df


class TestModuleFunctionMapping:
    """Ensure every registered module maps to a callable executor function."""

    def test_all_modules_have_functions(self):
        missing = [name for name in get_module_names() if _get_module_function(name) is None]
        assert not missing, f"Missing module function mappings: {missing}"


class TestWorkflowExecutor:
    """Smoke tests for plan execution."""

    @pytest.mark.asyncio
    async def test_individual_omics_pipeline(self, sample_data):
        microbiome_df, metabolome_df, metadata_df = sample_data
        planner = get_planner()
        plan = await planner.plan("Run individual omics profiling")

        executor = WorkflowExecutor()
        executor.set_session_data(microbiome_df, metabolome_df, metadata_df)

        events = []
        async for event in executor.execute(plan):
            events.append(event)

        completed = [e for e in events if e.event_type == "step_complete"]
        errors = [e for e in events if e.event_type == "step_error"]

        assert len(events) > 0
        assert events[0].event_type == "plan_accepted"
        assert events[-1].event_type == "complete"
        assert len(errors) == 0, f"Unexpected errors: {[e.payload for e in errors]}"
        assert len(completed) == len(plan.steps)


class TestDataValidatorModule:
    """The data_validator step must run the real validator, not a no-op."""

    def _validate(self, **kwargs):
        return _get_module_function("data_validator")(**kwargs)

    def test_clean_data_passes_and_reports_every_layer(self, sample_data):
        microbiome_df, metabolome_df, metadata_df = sample_data
        out = self._validate(df=microbiome_df, df2=metabolome_df, metadata_df=metadata_df)

        assert out["valid"] is True
        assert out["errors"] == []
        assert set(out["validated"]) == {"microbiome", "metabolome", "metadata"}
        # Real details, not an empty stub report.
        assert out["report"]["microbiome"]["details"]["total_samples"] == microbiome_df.shape[1]
        assert out["report"]["microbiome_vs_metadata"]["details"]["matched_samples"] == 10

    def test_negative_and_missing_abundances_are_errors(self, sample_data):
        microbiome_df, _, metadata_df = sample_data
        broken = microbiome_df.astype(float).copy()
        broken.iloc[0, 0] = -1.0
        broken.iloc[1, 1] = np.nan

        out = self._validate(df=broken, metadata_df=metadata_df)

        assert out["valid"] is False
        assert any("negative" in e for e in out["errors"])
        assert any("NA value" in e for e in out["errors"])

    def test_samples_not_matching_metadata_is_an_error(self, sample_data):
        microbiome_df, _, metadata_df = sample_data
        stranger = metadata_df.copy()
        stranger.index = [f"other{i}" for i in range(len(stranger))]

        out = self._validate(df=microbiome_df, metadata_df=stranger)

        assert out["valid"] is False
        assert any("No matching sample names" in e for e in out["errors"])

    def test_missing_group_column_is_an_error(self, sample_data):
        microbiome_df, _, metadata_df = sample_data
        out = self._validate(df=microbiome_df, metadata_df=metadata_df, group_column="Nope")

        assert out["valid"] is False
        assert any("Nope" in e for e in out["errors"])

    def test_no_feature_table_is_an_error(self):
        out = self._validate()
        assert out["valid"] is False
        assert out["errors"]

    def test_missing_metadata_is_a_warning_not_an_error(self, sample_data):
        microbiome_df, _, _ = sample_data
        out = self._validate(df=microbiome_df)

        assert out["valid"] is True
        assert any("no metadata table" in w for w in out["warnings"])

    @pytest.mark.asyncio
    async def test_failed_validation_fails_the_step_and_aborts_the_plan(self, sample_data):
        microbiome_df, _, metadata_df = sample_data
        broken = microbiome_df.astype(float).copy()
        broken.iloc[0, 0] = -1.0

        plan = ExecutionPlan(
            query="validate then analyse",
            steps=[
                PlanStep(id="v", module="data_validator"),
                PlanStep(id="a", module="microbiome_alpha", depends_on=["v"]),
            ],
        )
        executor = WorkflowExecutor(session_id="test-session")
        executor.set_session_data(broken, None, metadata_df)

        events = [e async for e in executor.execute(plan)]
        by_type = {}
        for e in events:
            by_type.setdefault(e.event_type, []).append(e)

        assert "v" in executor.failed_steps
        assert "v" not in executor.completed_steps
        assert any("negative" in e.payload.get("error", "") for e in by_type["step_error"])
        # Downstream analysis must not have run on rejected data.
        assert "a" not in executor.state
        assert by_type["complete"][0].payload["completed"] == 0
        # The rejection report itself is still available to the caller.
        assert executor.state["v"]["valid"] is False


class TestReportGeneratorModule:
    """The report_generator must never name a file that does not exist."""

    def _generate(self, **kwargs):
        return _get_module_function("report_generator")(**kwargs)

    def test_unsupported_format_reports_unavailable_without_a_path(self):
        out = self._generate(results=[{"job_type": "microbiome_pcoa"}], format="markdown")
        assert out["status"] == "unavailable"
        assert out["report_path"] is None
        assert "markdown" in out["reason"]

    def test_no_results_reports_unavailable_without_a_path(self):
        out = self._generate(results=[], format="pdf")
        assert out["status"] == "unavailable"
        assert out["report_path"] is None

    def test_pdf_report_is_written_to_disk(self, tmp_path, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
        out = self._generate(
            results=[{
                "job_type": "microbiome_pcoa",
                "test_method": "microbiome_pcoa",
                "parameters": {"distance_metric": "braycurtis"},
                "n_samples": 10,
                "n_features": 20,
            }],
            session_id="sess1",
            format="pdf",
        )

        assert out["status"] == "generated"
        report_path = Path(out["report_path"])
        assert report_path.exists() and report_path.stat().st_size > 0
        assert out["size_bytes"] == report_path.stat().st_size
        assert report_path.read_bytes().startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_executor_passes_completed_steps_in_plan_order(self, sample_data, tmp_path, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
        microbiome_df, metabolome_df, metadata_df = sample_data

        plan = ExecutionPlan(
            query="alpha then report",
            steps=[
                PlanStep(id="v", module="data_validator"),
                PlanStep(id="alpha", module="microbiome_alpha", depends_on=["v"]),
                PlanStep(id="rep", module="report_generator", depends_on=["alpha"],
                         params={"format": "pdf"}),
            ],
        )
        executor = WorkflowExecutor(session_id="sess2")
        executor.set_session_data(microbiome_df, metabolome_df, metadata_df)

        events = [e async for e in executor.execute(plan)]
        assert not [e for e in events if e.event_type == "step_error"]

        report = executor.state["rep"]
        assert report["status"] == "generated"
        assert report["modules"] == ["data_validator", "microbiome_alpha"]
        assert Path(report["report_path"]).exists()
