"""Smoke-test the 16 newly wired agent modules on synthetic data."""
import asyncio
import numpy as np
import pandas as pd

from app.agent.planner import PlanStep
from app.agent.executor import WorkflowExecutor

rng = np.random.default_rng(42)
samples = [f"S{i}" for i in range(24)]
mb = pd.DataFrame(
    rng.poisson(10, (40, 24)).astype(float),
    index=[f"g__Genus{i}" for i in range(40)],
    columns=samples,
)
met = pd.DataFrame(
    rng.lognormal(5, 1, (50, 24)),
    index=[f"Met{i}" for i in range(50)],
    columns=samples,
)
meta = pd.DataFrame({
    "Visit": ["T4"] * 12 + ["T5"] * 12,
    "source_type": ["oral"] * 12 + ["gut"] * 12,
}, index=samples)

MODULES = [
    ("anosim", {"group_column": "Visit"}),
    ("random_forest", {"group_column": "Visit"}),
    ("heatmap", {"top_n": 20}),
    ("volcano", {"group_column": "Visit", "reference_group": "T4"}),
    ("aldex2", {"group_column": "Visit"}),
    ("songbird", {"group_column": "Visit", "epochs": 50}),
    ("enterotype", {"n_clusters": 2}),
    ("rarefaction", {"group_column": "Visit", "steps": 5, "iterations": 2}),
    ("taxonomy_bar", {"group_column": "Visit", "top_n": 8}),
    ("mofa", {"n_factors": 2, "group_column": "Visit"}),
    ("diablo", {"group_column": "Visit", "n_components": 2}),
    ("wgcna", {"min_module_size": 5}),
    ("unifrac", {"group_column": "Visit", "n_permutations": 49}),
    ("source_tracking", {"source_column": "source_type"}),
    ("upset", {"group_column": "Visit"}),
]


async def main():
    for module, params in MODULES:
        ex = WorkflowExecutor()
        ex.set_session_data(mb, met, meta)
        step = PlanStep(id=f"s_{module}", module=module, params=params,
                        description=module, depends_on=[])
        events = await ex._execute_step_with_events(step)
        err = next((e for e in events if e.event_type == "step_error"), None)
        if err:
            print(f"FAIL {module}: {err.payload['error'][:160]}")
            continue
        res = ex.get_result(f"s_{module}")
        err_msg = res.get("error") if isinstance(res, dict) else None
        has_plot = isinstance(res, dict) and bool(res.get("plot_data"))
        print(f"{'WARN' if err_msg else 'OK  '} {module}: plot={has_plot} err={err_msg}")


asyncio.run(main())
