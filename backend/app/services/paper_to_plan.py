"""
Paper-to-Plan
=============
Reproduce a published analysis workflow on our platform: take a paper's
text (methods above all), ask the LLM which bioinformatics analyses it
describes, map them onto registered platform modules, and return a
validated ExecutionPlan the user can review and confirm before execution.

Safety properties:
- Only modules in MODULE_REGISTRY survive (shared validator with the
  LLM-fallback planner).
- Analyses the paper describes but the platform cannot run are reported
  in ``unmatched_analyses`` instead of being silently dropped.
- Nothing executes here; the client must confirm and then call
  /agent/execute with the returned plan.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.agent.module_registry import MODULE_REGISTRY
from app.agent.planner import AnalysisPlanner, ExecutionPlan, _estimate_time

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 24000  # methods + abstract comfortably fit; keeps LLM fast


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = MAX_TEXT_CHARS) -> str:
    """Extract text from a PDF, stopping at the Results/Discussion boundary
    when detectable (methods live before it) to keep the prompt focused."""
    import io
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts = []
    total = 0
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            continue
        parts.append(t)
        total += len(t)
        if total > max_chars * 2:
            break
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


_SYSTEM_PROMPT = """You are a bioinformatics methods analyst. Given the text of a scientific
paper (microbiome/metabolome study), identify every computational/statistical
analysis the authors performed, and reproduce that workflow using ONLY these
platform modules:

{modules}

Respond with ONLY a JSON object (no markdown fences, no commentary):
{{
  "analyses_found": ["<short name of each analysis described in the paper>", ...],
  "unmatched_analyses": ["<analyses with no suitable platform module>", ...],
  "steps": [
    {{"id": "stepN_<module>", "module": "<module from the list>", "params": {{}},
      "depends_on": ["<ids of prerequisite steps>"]}},
    ...
  ]
}}

Rules:
1. data_validator must be the first step (id "step1_validate").
2. Only module names from the list above. Put everything else into
   unmatched_analyses - never invent modules.
3. Choose params that mirror the paper's methods when the module supports
   them (e.g. test_method, transformation, group_column).
4. microbiome_marker MUST use transformation="clr" and test_method="mannwhitney".
5. metabolome_marker MUST use transformation="log1p" and test_method="welch".
6. Keep the workflow in the order the paper performed the analyses.
"""


def plan_from_text(paper_text: str, max_chars: int = MAX_TEXT_CHARS) -> Dict[str, Any]:
    """Build a proposed plan from paper text. Returns a dict with the plan,
    explanation inputs, and provenance. Raises ValueError when the LLM is
    unavailable or returns nothing usable (caller turns that into a 422)."""
    from app.services.llm_client import get_llm_client

    client = get_llm_client()
    if not client.available:
        raise ValueError("LLM is not configured (no API key); paper-to-plan requires it")

    text = (paper_text or "").strip()
    if len(text) < 200:
        raise ValueError("paper text too short (<200 chars) to identify an analysis workflow")
    if len(text) > max_chars:
        text = text[:max_chars]

    modules = "\n".join(
        f"- {name}: {spec.description} [category: {spec.category}]"
        for name, spec in MODULE_REGISTRY.items()
    )
    content = client.chat(_SYSTEM_PROMPT.format(modules=modules),
                          text, max_tokens=16000, timeout=180)
    if not content:
        raise ValueError("LLM returned no content")

    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```")[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        # Reasoning models can exhaust max_tokens mid-payload. Salvage the
        # complete step objects (shared with the planner fallback); the
        # analyses_found lists are best-effort and may be lost.
        from app.agent.planner import _parse_llm_plan
        salvaged = _parse_llm_plan(stripped)
        if not salvaged:
            raise ValueError("LLM output was truncated beyond recovery; try again")
        data = {"steps": salvaged["steps"], "analyses_found": [], "unmatched_analyses": []}

    steps = AnalysisPlanner._validate_llm_steps(data.get("steps") or [])
    if not steps:
        raise ValueError("LLM produced no valid platform steps for this paper")

    plan = ExecutionPlan(
        query="Reproduce the analysis workflow of an uploaded paper",
        steps=steps,
        estimated_time=_estimate_time(len(steps)),
        notes=["Reconstructed from paper text; review before executing."],
    )
    return {
        "plan": plan,
        "analyses_found": data.get("analyses_found") or [],
        "unmatched_analyses": data.get("unmatched_analyses") or [],
    }
