"""
Workflow Explainer
==================
Renders an ExecutionPlan into natural language so users who do not know the
platform's analysis pipeline can see -- step by step -- what will run, in
what order, with which parameters, and why.

Fully deterministic: explanations are built from MODULE_REGISTRY metadata
(category, description, input requirements, output spec) and the plan's own
params, so the explanation can never drift from what the executor will do.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.agent.module_registry import MODULE_REGISTRY, get_module_spec


def _fmt_params(params: Dict[str, Any]) -> str:
    if not params:
        return "default parameters"
    return ", ".join(f"{k}={v!r}" for k, v in params.items())


def _fmt_requirements(req: Dict[str, Any]) -> str:
    parts = []
    for slot, need in (req or {}).items():
        if need == "required":
            parts.append(f"{slot} (required)")
        elif need == "optional":
            parts.append(f"{slot} (optional)")
    return ", ".join(parts) if parts else "no specific input requirement"


def explain_plan(plan) -> Dict[str, Any]:
    """Explain an ExecutionPlan. Accepts the dataclass or its dict form."""
    steps = plan.steps if hasattr(plan, "steps") else plan.get("steps", [])

    explained_steps: List[Dict[str, Any]] = []
    for i, step in enumerate(steps, 1):
        if hasattr(step, "module"):
            module, params, depends = step.module, step.params, step.depends_on
            step_id = step.id
        else:
            module = step.get("module")
            params = step.get("params") or {}
            depends = step.get("depends_on") or []
            step_id = step.get("id", f"step{i}")

        spec = get_module_spec(module) or MODULE_REGISTRY.get(module)
        entry = {
            "order": i,
            "id": step_id,
            "module": module,
            "what": (spec.description if spec else
                     "(no description; module not in registry)"),
            "category": spec.category if spec else None,
            "parameters": _fmt_params(params),
            "inputs": _fmt_requirements(spec.input_requirements if spec else {}),
        }
        if depends:
            entry["runs_after"] = depends
        if spec and spec.output_spec:
            entry["produces"] = spec.output_spec
        explained_steps.append(entry)

    clarification = getattr(plan, "clarification_needed", None)
    if clarification is None and isinstance(plan, dict):
        clarification = plan.get("clarification_needed", False)

    n = len(explained_steps)
    if clarification:
        overview = ("The planner could not determine a specific analysis from "
                    "the request. Rephrase with an explicit goal, e.g. "
                    "'compare alpha diversity between groups' or "
                    "'find differential species in disease vs control'.")
    elif n == 0:
        overview = "Empty plan - nothing would run."
    else:
        cats = []
        for s in explained_steps:
            if s["category"] and s["category"] not in cats:
                cats.append(s["category"])
        overview = (f"{n} step{'s' if n > 1 else ''} covering "
                    f"{', '.join(cats) if cats else 'analysis'}; "
                    f"steps run in dependency order as listed.")

    return {
        "overview": overview,
        "n_steps": n,
        "clarification_needed": bool(clarification),
        "steps": explained_steps,
    }
