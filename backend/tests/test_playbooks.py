"""Playbook regression: curated study-type plan templates must keep
instantiating and executing on real session-shaped data.

Two layers are pinned:

1. Instantiation — placeholders resolve through the same column-snapping
   contract as paper2agent (user mapping wins, synonym snapping second,
   honest error when a required role is unresolvable; reference levels
   default to the first sorted level of the resolved group column).
2. Execution — instantiated plans are replayed through the real
   WorkflowExecutor against Huang-style synthetic data; executor changes
   that break a playbook fail here, same contract as the paper fixtures.

No LLM calls are made anywhere in this file.
"""
import numpy as np
import pandas as pd
import pytest

from app.agent.executor import WorkflowExecutor
from app.agent.planner import ExecutionPlan, PlanStep
from app.agent.playbooks import (
    PlaybookError,
    declared_roles,
    get_playbook,
    instantiate_playbook,
    list_playbooks,
)


@pytest.fixture
def huang_like_metadata():
    """Huang-style metadata: Timepoint(DAY0/DAY14), Bleeding, Host_ID, Group."""
    samples = [f"S{i}" for i in range(24)]
    return pd.DataFrame(
        {
            "Timepoint": ["DAY0"] * 12 + ["DAY14"] * 12,
            "Bleeding": ["High", "Low"] * 12,
            "Host_ID": [f"H{i % 12}" for i in range(24)],
            "Group": ["High_bleeder"] * 12 + ["Low_bleeder"] * 12,
        },
        index=samples,
    )


@pytest.fixture
def huang_like_data(huang_like_metadata):
    rng = np.random.default_rng(42)
    samples = list(huang_like_metadata.index)
    microbiome_df = pd.DataFrame(
        rng.poisson(10, (40, len(samples))).astype(float),
        index=[f"g__Genus{i}" for i in range(40)],
        columns=samples,
    )
    metabolome_df = pd.DataFrame(
        rng.lognormal(5, 1, (50, len(samples))),
        index=[f"Met{i}" for i in range(50)],
        columns=samples,
    )
    return microbiome_df, metabolome_df, huang_like_metadata


def _to_execution_plan(plan_dict) -> ExecutionPlan:
    return ExecutionPlan(
        query=plan_dict["query"],
        steps=[PlanStep(id=s["id"], module=s["module"], params=s.get("params") or {},
                        depends_on=s.get("depends_on") or [],
                        description=s.get("description") or "")
               for s in plan_dict["steps"]],
        estimated_time="",
    )


async def _execute(plan_dict, data, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    mb, met, md = data
    executor = WorkflowExecutor(session_id="playbook-regression")
    executor.set_session_data(mb, met, md)
    by_step, finals = {}, []
    async for ev in executor.execute(_to_execution_plan(plan_dict)):
        d = ev.to_dict()
        if ev.step_id:
            by_step[ev.step_id] = d
        if ev.event_type == "complete":
            finals.append(d)
    return executor, by_step, finals


class TestPlaybookLibrary:
    def test_playbooks_discovered(self):
        ids = [p["id"] for p in list_playbooks()]
        assert "longitudinal_multiomics" in ids
        assert "case_control_16s" in ids

    def test_all_playbooks_schema_valid(self):
        # get_playbook raises on unknown ids; _load_all validates every file
        # at import: modules registered, unique ids, deps resolvable.
        for p in list_playbooks():
            pb = get_playbook(p["id"])
            assert pb["steps"], p["id"]
            assert declared_roles(pb), f"{p['id']} declares no placeholders"
            for s in pb["steps"]:
                assert s["module"] and s["id"]

    def test_declared_roles_covered_by_column_docs(self):
        # Every placeholder used by steps must be documented in
        # required_columns or optional_columns, or the confirm screen cannot
        # explain what the user must supply.
        for p in list_playbooks():
            pb = get_playbook(p["id"])
            documented = set(pb.get("required_columns") or {}) | set(
                pb.get("optional_columns") or {})
            undocumented = set(declared_roles(pb)) - documented
            assert not undocumented, f"{p['id']}: undocumented roles {undocumented}"


class TestLongitudinalInstantiation:
    def test_roles_snap_to_huang_columns(self, huang_like_metadata):
        result = instantiate_playbook("longitudinal_multiomics", huang_like_metadata)
        roles = result["resolved_roles"]
        assert roles["time_column"] == "Timepoint"
        assert roles["subject_column"] == "Host_ID"
        # reference level defaults to the baseline level of the time column
        assert roles["reference_level"] == "DAY0"

    def test_placeholders_substituted_everywhere(self, huang_like_metadata):
        result = instantiate_playbook("longitudinal_multiomics", huang_like_metadata)
        for step in result["plan"]["steps"]:
            for v in step["params"].values():
                values = v if isinstance(v, list) else [v]
                for x in values:
                    assert not (isinstance(x, str) and x.startswith("{")), (
                        f"unresolved placeholder in {step['id']}: {x}")

    def test_user_mapping_wins(self, huang_like_metadata):
        result = instantiate_playbook(
            "longitudinal_multiomics", huang_like_metadata,
            column_mapping={"time_column": "Bleeding"})
        assert result["resolved_roles"]["time_column"] == "Bleeding"
        assert result["resolved_roles"]["reference_level"] == "High"

    def test_bad_user_mapping_is_honest_error(self, huang_like_metadata):
        with pytest.raises(PlaybookError, match="不在元数据列中"):
            instantiate_playbook(
                "longitudinal_multiomics", huang_like_metadata,
                column_mapping={"time_column": "Nonexistent"})

    def test_missing_subject_column_is_honest_error(self):
        md = pd.DataFrame({"Timepoint": ["T0", "T1"]}, index=["S1", "S2"])
        with pytest.raises(PlaybookError, match="subject_column"):
            instantiate_playbook("longitudinal_multiomics", md)


class TestCaseControlInstantiation:
    def test_group_snaps_and_reference_defaults(self, huang_like_metadata):
        result = instantiate_playbook("case_control_16s", huang_like_metadata)
        roles = result["resolved_roles"]
        assert roles["group_column"] == "Group"
        assert roles["reference_group"] == "High_bleeder"

    def test_missing_group_column_is_honest_error(self):
        md = pd.DataFrame({"Age": [50, 60]}, index=["S1", "S2"])
        with pytest.raises(PlaybookError, match="group_column"):
            instantiate_playbook("case_control_16s", md)


class TestPlaybookExecution:
    @pytest.mark.asyncio
    async def test_longitudinal_plan_executes_end_to_end(
            self, huang_like_data, tmp_path, monkeypatch):
        result = instantiate_playbook("longitudinal_multiomics", huang_like_data[2])
        executor, by_step, finals = await _execute(
            result["plan"], huang_like_data, tmp_path, monkeypatch)
        assert finals, "no completion event"
        payload = finals[-1]["payload"]
        assert payload["failed"] == 0, (
            f"failed steps: {[s for s, d in by_step.items() if d.get('event_type') == 'step_error']}")
        assert "step13_report" in executor.completed_steps

    @pytest.mark.asyncio
    async def test_case_control_plan_executes_end_to_end(
            self, huang_like_data, tmp_path, monkeypatch):
        result = instantiate_playbook("case_control_16s", huang_like_data[2])
        executor, by_step, finals = await _execute(
            result["plan"], huang_like_data, tmp_path, monkeypatch)
        assert finals, "no completion event"
        payload = finals[-1]["payload"]
        assert payload["failed"] == 0
        assert "step13_report" in executor.completed_steps

    @pytest.mark.asyncio
    async def test_marker_uses_snapped_group_and_reference(
            self, huang_like_data, tmp_path, monkeypatch):
        """The marker step must run with Group/High_bleeder, proving the
        placeholder substitution reaches module kwargs (not just the plan)."""
        result = instantiate_playbook("case_control_16s", huang_like_data[2])
        marker = next(s for s in result["plan"]["steps"] if s["id"] == "step7_marker")
        assert marker["params"]["group_column"] == "Group"
        assert marker["params"]["reference_group"] == "High_bleeder"
        executor, by_step, finals = await _execute(
            result["plan"], huang_like_data, tmp_path, monkeypatch)
        assert "step7_marker" in executor.completed_steps
