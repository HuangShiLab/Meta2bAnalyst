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
import re
from typing import Any, Dict, List, Optional

from app.agent.module_registry import MODULE_REGISTRY
from app.agent.planner import AnalysisPlanner, ExecutionPlan, _estimate_time

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 24000  # methods + abstract comfortably fit; keeps LLM fast
_FULL_TEXT_CAP = 800_000  # bound pypdf work on book-length PDFs

# A standalone Methods heading line. Nature-format papers print Methods at
# the very end; author manuscripts prefix/suffix line numbers ("Methods 691").
# The trailing-$ anchor keeps citation journal names ("Nat Methods 15, ...")
# from matching.
_METHODS_HEADING = re.compile(
    r"(?im)^\s*(?:\d+\s*[.:-]?\s*)?(?:materials\s+and\s+|star\s+)?methods\b\s*\d*\s*$"
)

# A Statistical/Bioinformatics analysis subheading line inside Methods. Long
# methods sections lead with cohort and wet-lab protocols; the computational
# analyses the planner maps to modules are described under these subheadings.
_STATS_HEADING = re.compile(
    r"(?im)^\s*(?:\d+\s*[.:-]?\s*)?(?:statistical|bioinformatics?|computational)\s+"
    r"(?:analysis|analyses|methods)\b[^\n]{0,60}$"
)

# Bounds the Methods section so a "Statistical analysis" citation line inside
# the References is never mistaken for the real subheading.
_REFERENCES_HEADING = re.compile(
    r"(?im)^\s*(?:\d+\s*[.:-]?\s*)?references\s*$"
)


def _window_text(full: str, max_chars: int) -> str:
    """Budget the paper text: opening (title/abstract/intro) plus Methods.

    Nature-format papers print Methods after the Discussion, so a naive
    first-N-chars cut misses the very text the planner needs.  When a
    standalone Methods heading is found, return the first quarter of the
    budget from the top of the paper and the rest starting at the Methods
    heading (the last such heading - earlier hits are usually in-text
    references or TOC entries).

    Methods sections longer than their window lead with cohort and wet-lab
    subsections; when a statistical-analysis subheading sits at or beyond the
    window's tail, recentre the window on it - that is where the analyses the
    planner must map to modules are described.
    """
    if len(full) <= max_chars:
        return full
    matches = list(_METHODS_HEADING.finditer(full))
    if not matches:
        return full[:max_chars]

    head_budget = max_chars // 4
    methods_budget = max_chars - head_budget
    head = full[:head_budget]
    methods_start = matches[-1].start()
    ref = _REFERENCES_HEADING.search(full, methods_start)
    methods_end = ref.start() if ref else len(full)

    window_start = methods_start
    stats = _STATS_HEADING.search(full, methods_start, methods_end)
    if stats and stats.start() > window_start + methods_budget - 4000:
        window_start = max(methods_start, stats.start() - 2500)

    methods = full[window_start:min(window_start + methods_budget, methods_end)]
    return head + "\n\n[... METHODS SECTION ...]\n\n" + methods


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = MAX_TEXT_CHARS) -> str:
    """Extract paper text for the planner: opening plus the Methods section
    (see _window_text for the windowing policy)."""
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
        if total > _FULL_TEXT_CAP:
            break
    full = "\n".join(parts)
    return _window_text(full, max_chars)


_SYSTEM_PROMPT = """You are a bioinformatics methods analyst. Given the text of a scientific
paper (microbiome/metabolome study), identify every computational/statistical
analysis the authors performed, and reproduce that workflow using ONLY these
platform modules (parameter names and enum options are part of each module's
contract - use them verbatim):

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
3. Use ONLY the parameter names listed for each module; parameters shown as
   enum must use one of the listed options. Do not invent parameters - extra
   keys are ignored and your intent is lost.
4. For parameters that name a metadata column (group_column, subject_column,
   time_column, ...), use the paper's own wording (e.g. "timepoint"); the
   platform resolves it against the uploaded metadata at execution time.
5. microbiome_marker MUST use transformation="clr" and test_method="mannwhitney".
6. metabolome_marker MUST use transformation="log1p" and test_method="welch".
7. report_generator only supports format="pdf".
8. Keep the workflow in the order the paper performed the analyses.
9. Omit a parameter entirely when the paper gives no value for it; do not
   guess defaults.
"""


def _render_module_list() -> str:
    """Module catalogue for the prompt, including each module's parameter
    schema so the LLM picks real parameter names instead of guessing."""
    lines = []
    for name, spec in MODULE_REGISTRY.items():
        line = f"- {name}: {spec.description} [category: {spec.category}]"
        if spec.parameters:
            parts = []
            for pname, pspec in spec.parameters.items():
                if not isinstance(pspec, dict):
                    parts.append(pname)
                    continue
                ptype = pspec.get("type", "any")
                if ptype == "enum" and pspec.get("options"):
                    opts = "|".join(str(o) for o in pspec["options"][:8])
                    parts.append(f"{pname}(enum:{opts})")
                elif pspec.get("default") is not None:
                    parts.append(f"{pname}({ptype},default={pspec['default']})")
                else:
                    parts.append(f"{pname}({ptype})")
            line += " params: " + ", ".join(parts)
        lines.append(line)
    return "\n".join(lines)


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

    content = client.chat(_SYSTEM_PROMPT.format(modules=_render_module_list()),
                          text, max_tokens=8192, timeout=280)
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
