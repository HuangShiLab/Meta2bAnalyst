"""
Agent API Routes
================
Provides endpoints for the Agent orchestration layer:
- POST /agent/plan: Generate analysis plan from natural language
- POST /agent/execute: Execute plan with SSE streaming
- POST /agent/analyze: One-shot plan + execute
- GET  /agent/modules: List available analysis modules
- POST /agent/recommend: L3 method recommendation
- POST /agent/interpret: L4 result interpretation
- POST /agent/write-paper: L5 paper section generation
- POST /agent/write-paper/full: L5 full manuscript draft
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Request
from app.database import get_db
from sqlalchemy.orm import Session as DBSession
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent import (
    get_planner,
    WorkflowExecutor,
    ResultIntegrator,
    ExecutionEvent,
    get_module_names,
    get_module_spec,
    MODULE_REGISTRY,
)
from app.api.routes.analysis import get_db, get_dataframe, get_dataframe_by_name, get_metadata_df
from app.services.agent_engine import AgentEngine
from app.services.data_parser import parse_data_file


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


# ───────────────────────────────────────────────────────────────
# SCHEMAS
# ───────────────────────────────────────────────────────────────

class PlanRequest(BaseModel):
    """Request to generate an analysis plan."""
    query: str = Field(..., description="Natural language description of desired analysis")
    session_id: Optional[str] = Field(None, description="Session ID for data context")
    use_llm: bool = Field(False, description="Use LLM-based planner (requires API key)")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")


class PlanResponse(BaseModel):
    """Response containing the execution plan."""
    query: str
    n_steps: int
    steps: list
    estimated_time: str
    notes: list


class ExecuteRequest(BaseModel):
    """Request to execute a plan."""
    session_id: str = Field(..., description="Session ID with uploaded data")
    plan: Optional[Dict[str, Any]] = Field(None, description="Pre-generated plan (if None, will be generated from query)")
    query: Optional[str] = Field(None, description="Query to generate plan (used if plan is None)")


class AnalyzeRequest(BaseModel):
    """One-shot analyze request (plan + execute, non-streaming)."""
    query: str = Field(..., description="Natural language analysis request")
    session_id: str = Field(..., description="Session ID with uploaded data")
    use_llm: bool = Field(False, description="Use LLM planner")
    generate_report: bool = Field(True, description="Generate integrated report")


class AnalyzeResponse(BaseModel):
    """Response from one-shot analysis."""
    query: str
    plan: Dict[str, Any]
    results: Dict[str, Any]
    report: Optional[Dict[str, Any]] = None
    execution_time: float


# ── L3 / L4 / L5 Schemas ───────────────────────────────────────

class RecommendRequest(BaseModel):
    """L3 – Request method recommendations."""
    data_summary: Dict[str, Any] = Field(
        ...,
        description="Data characteristics: data_type, sample_size, has_metadata, study_design, n_groups, feature_count, sequencing_platform",
    )
    research_question: str = Field(..., description="Natural-language research goal")
    top_k: int = Field(default=5, ge=1, le=20, description="Maximum number of recommendations to return")


class RecommendResponse(BaseModel):
    """L3 – Ranked method recommendations."""
    recommendations: List[Dict[str, Any]]
    query: str
    data_type: Optional[str]
    sample_size: Optional[int]
    study_design: Optional[str]


class InterpretRequest(BaseModel):
    """L4 – Request result interpretation."""
    analysis_type: str = Field(
        ...,
        description="Analysis type: alpha, beta, differential, pcoa, nmds, lefse, ancom, deseq2, aldex2, maaslin2, correlation, network, functional, metabolome_pca, metabolome_plsda",
    )
    statistics: Dict[str, Any] = Field(..., description="Analysis-specific summary statistics")
    plot_data: Optional[Dict[str, Any]] = Field(default=None, description="Optional visualisation metadata")


class InterpretResponse(BaseModel):
    """L4 – Natural-language interpretation."""
    analysis_type: str
    summary: str
    detailed: str
    clinical_relevance: Optional[str]
    caveats: List[str]
    follow_up_suggestions: List[str]


class WritePaperRequest(BaseModel):
    """L5 – Request manuscript section generation."""
    section_type: str = Field(
        ...,
        description="Section to generate: abstract, introduction, methods, results, discussion, conclusions, keywords",
    )
    results_summary: Dict[str, Any] = Field(..., description="Study descriptors and key findings")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional narrative context")


class WritePaperResponse(BaseModel):
    """L5 – Generated manuscript section."""
    section_type: str
    title: str
    content: str
    word_count: int
    keywords: List[str]


class FullPaperRequest(BaseModel):
    """L5 – Request full manuscript draft."""
    results_summary: Dict[str, Any] = Field(..., description="Study metadata and findings")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context")


class FullPaperResponse(BaseModel):
    """L5 – Complete manuscript with all sections."""
    title: str
    sections: Dict[str, Dict[str, Any]]


# ───────────────────────────────────────────────────────────────
# MODULE DISCOVERY
# ───────────────────────────────────────────────────────────────

@router.get("/modules", response_model=Dict[str, Any])
async def list_modules():
    """List all available analysis modules with their metadata."""
    modules = {}
    for name, spec in MODULE_REGISTRY.items():
        modules[name] = {
            "name": spec.name,
            "description": spec.description,
            "category": spec.category,
            "input_requirements": spec.input_requirements,
            "parameters": spec.parameters,
            "output_spec": spec.output_spec,
            "constraints": spec.constraints,
            "depends_on": spec.depends_on,
        }
    return {
        "modules": modules,
        "categories": list(set(spec.category for spec in MODULE_REGISTRY.values())),
        "total": len(modules),
    }


@router.get("/modules/{module_name}", response_model=Dict[str, Any])
async def get_module_detail(module_name: str):
    """Get detailed information about a specific module."""
    spec = get_module_spec(module_name)
    if not spec:
        raise HTTPException(status_code=404, detail=f"Module '{module_name}' not found")
    return {
        "name": spec.name,
        "description": spec.description,
        "category": spec.category,
        "input_requirements": spec.input_requirements,
        "parameters": spec.parameters,
        "output_spec": spec.output_spec,
        "constraints": spec.constraints,
        "depends_on": spec.depends_on,
    }


# ───────────────────────────────────────────────────────────────
# PLANNING
# ───────────────────────────────────────────────────────────────

@router.post("/plan", response_model=PlanResponse)
async def create_plan(request: PlanRequest, db: DBSession = Depends(get_db)):
    """
    Generate an execution plan from a natural language query.

    Example:
        {
            "query": "Find differential markers between Day 0 and Day 21",
            "session_id": "abc123",
            "use_llm": false
        }
    """
    try:
        planner = get_planner(use_llm=request.use_llm)

        # Build context from session if available
        context = request.context or {}
        if request.session_id:
            context["session_id"] = request.session_id
            
            # Get session files for data-aware planning
            try:
                from app.models import DataFile
                files = (
                    db.query(DataFile)
                    .filter(DataFile.session_id == request.session_id)
                    .all()
                )
                if files:
                    context["session_files"] = [f.file_name for f in files]
                    context["file_types"] = [f.file_type for f in files if f.file_type]
            except Exception:
                pass

        plan = await planner.plan(request.query, context)

        return PlanResponse(
            query=plan.query,
            n_steps=len(plan.steps),
            steps=[
                {
                    "id": s.id,
                    "module": s.module,
                    "params": s.params,
                    "depends_on": s.depends_on,
                    "description": s.description,
                }
                for s in plan.steps
            ],
            estimated_time=plan.estimated_time,
            notes=plan.notes,
        )

    except Exception as e:
        logger.error(f"Planning failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Planning failed: {str(e)}")


# ───────────────────────────────────────────────────────────────
# EXECUTION (SSE STREAMING)
# ───────────────────────────────────────────────────────────────

def _load_session_data(session_id: str, db: DBSession):
    """Load microbiome, metabolome, and metadata dataframes for a session."""
    # Try dedicated file types first
    from app.models import DataFile

    mb_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id, DataFile.file_type == "microbiome")
        .order_by(DataFile.id.desc())
        .first()
    )
    met_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id, DataFile.file_type == "metabolome")
        .order_by(DataFile.id.desc())
        .first()
    )

    microbiome_df = None
    if mb_file:
        try:
            microbiome_df, _ = parse_data_file(Path(mb_file.file_path), use_chunks=True)
        except Exception:
            pass

    metabolome_df = None
    if met_file:
        try:
            metabolome_df, _ = parse_data_file(Path(met_file.file_path), use_chunks=True)
        except Exception:
            pass

    # Fallback: filename patterns
    if microbiome_df is None:
        microbiome_df = get_dataframe_by_name(session_id, db, "microbiome") or \
                        get_dataframe_by_name(session_id, db, "mb")
    if metabolome_df is None:
        metabolome_df = get_dataframe_by_name(session_id, db, "metabolome") or \
                        get_dataframe_by_name(session_id, db, "met")

    metadata_df = get_metadata_df(session_id, db)

    # Final fallback: if only one feature table exists, use it as microbiome
    if microbiome_df is None and metabolome_df is None:
        try:
            microbiome_df = get_dataframe(session_id, db)
        except Exception:
            pass

    return microbiome_df, metabolome_df, metadata_df


async def _execute_workflow_stream(
    session_id: str,
    plan_dict: Optional[Dict[str, Any]],
    query: Optional[str],
    db: DBSession,
):
    """
    Internal generator for workflow execution with SSE.
    Yields SSE-formatted strings.
    """
    from app.agent.planner import ExecutionPlan, PlanStep

    # Get plan
    if plan_dict:
        steps = [PlanStep(**s) for s in plan_dict.get("steps", [])]
        plan = ExecutionPlan(
            query=plan_dict.get("query", "custom plan"),
            steps=steps,
            estimated_time=plan_dict.get("estimated_time", ""),
        )
    elif query:
        planner = get_planner()
        plan = await planner.plan(query)
    else:
        yield "data: " + json.dumps({"event_type": "error", "payload": {"error": "No plan or query provided"}}) + "\n\n"
        return

    # Load data
    microbiome_df, metabolome_df, metadata_df = _load_session_data(session_id, db)

    # Execute
    executor = WorkflowExecutor()
    executor.set_session_data(microbiome_df, metabolome_df, metadata_df)

    async for event in executor.execute(plan):
        data = {
            "event_type": event.event_type,
            "step_id": event.step_id,
            "timestamp": event.timestamp,
            "payload": event.payload,
        }
        yield "data: " + json.dumps(data, default=str) + "\n\n"


@router.post("/execute")
async def execute_plan_stream(request: ExecuteRequest, db: DBSession = Depends(get_db)):
    """
    Execute an analysis plan with Server-Sent Events (SSE) streaming.

    Returns a stream of events:
    - plan_accepted: Plan received and validated
    - step_start: A step begins execution
    - step_complete: A step finishes successfully
    - step_error: A step failed
    - review_request: Human review needed (e.g., borderline p-value)
    - complete: All steps finished

    Example request:
        {
            "session_id": "abc123",
            "query": "Run full multi-omics pipeline"
        }
    """
    return StreamingResponse(
        _execute_workflow_stream(
            request.session_id,
            request.plan,
            request.query,
            db,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ───────────────────────────────────────────────────────────────
# ONE-SHOT ANALYZE
# ───────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_one_shot(request: AnalyzeRequest, db: DBSession = Depends(get_db)):
    """
    One-shot analysis: plan + execute + integrate (non-streaming).

    Best for simple requests that complete quickly.
    For long workflows, use /execute with SSE streaming.
    """
    import time
    start_time = time.time()

    try:
        # Plan
        planner = get_planner(use_llm=request.use_llm)
        plan = await planner.plan(request.query)

        # Load data
        microbiome_df, metabolome_df, metadata_df = _load_session_data(request.session_id, db)

        # Execute (collect all events)
        executor = WorkflowExecutor()
        executor.set_session_data(microbiome_df, metabolome_df, metadata_df)

        events = []
        async for event in executor.execute(plan):
            events.append(event)
            if event.event_type == "complete":
                break

        # Build results
        all_results = executor.get_all_results()

        # Generate report
        report = None
        if request.generate_report:
            integrator = ResultIntegrator()
            report = integrator.integrate(all_results, plan)

        elapsed = time.time() - start_time

        return AnalyzeResponse(
            query=request.query,
            plan={
                "n_steps": len(plan.steps),
                "steps": [{"id": s.id, "module": s.module} for s in plan.steps],
            },
            results=all_results,
            report=report,
            execution_time=elapsed,
        )

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ───────────────────────────────────────────────────────────────
# TEMPLATES
# ───────────────────────────────────────────────────────────────

@router.get("/templates", response_model=Dict[str, Any])
async def list_templates():
    """List available analysis templates."""
    from app.agent.planner import ANALYSIS_TEMPLATES

    templates = {}
    for t in ANALYSIS_TEMPLATES:
        templates[t["name"]] = {
            "name": t["name"],
            "description": t["description"],
            "n_steps": len(t["steps"]),
            "modules": [s["module"] for s in t["steps"]],
        }

    return {
        "templates": templates,
        "total": len(templates),
    }


# ════════════════════════════════════════════════════════════════
# L3 / L4 / L5 – Intelligent Analysis Engine Routes
# ════════════════════════════════════════════════════════════════

# Lazy singleton for the rule-based engine
_agent_engine: Optional[AgentEngine] = None


def _get_agent_engine() -> AgentEngine:
    global _agent_engine
    if _agent_engine is None:
        _agent_engine = AgentEngine()
    return _agent_engine


# ── L3: Method Recommendation ────────────────────────────────────

@router.post("/recommend", response_model=RecommendResponse)
async def recommend_methods(request: RecommendRequest):
    """
    L3 – Recommend optimal analysis methods given data characteristics
    and a research question.

    Example:
        {
            "data_summary": {
                "data_type": "amplicon",
                "sample_size": 48,
                "has_metadata": true,
                "study_design": "cross-sectional",
                "n_groups": 2
            },
            "research_question": "Find differential markers between treatment and control",
            "top_k": 5
        }
    """
    try:
        engine = _get_agent_engine()
        result = engine.recommend_methods(
            data_summary=request.data_summary,
            research_question=request.research_question,
            top_k=request.top_k,
        )
        return RecommendResponse(**result)
    except Exception as e:
        logger.error(f"Method recommendation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}")


# ── L4: Result Interpretation ────────────────────────────────────

@router.post("/interpret", response_model=InterpretResponse)
async def interpret_results(request: InterpretRequest):
    """
    L4 – Generate natural-language interpretation of analysis results.

    Example:
        {
            "analysis_type": "alpha",
            "statistics": {
                "metric": "Shannon",
                "pvalue": 0.003,
                "direction": "lower",
                "group_name": "treatment",
                "reference_group": "control",
                "cohen_d": -0.85,
                "sample_size": 24
            }
        }
    """
    try:
        engine = _get_agent_engine()
        result = engine.interpret_results(
            analysis_type=request.analysis_type,
            statistics=request.statistics,
            plot_data=request.plot_data,
        )
        return InterpretResponse(**result)
    except Exception as e:
        logger.error(f"Result interpretation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Interpretation failed: {str(e)}")


# ── L5: Paper Writing ────────────────────────────────────────────

@router.post("/write-paper", response_model=WritePaperResponse)
async def write_paper_section(request: WritePaperRequest):
    """
    L5 – Generate a publication-ready manuscript section.

    Example:
        {
            "section_type": "results",
            "results_summary": {
                "title": "Gut microbiome shifts in antibiotic-treated mice",
                "n_samples": 48,
                "data_type": "16S rRNA amplicon",
                "key_findings": [
                    "Alpha diversity (Shannon) was significantly reduced in the treatment group (p = 0.003).",
                    "Beta-diversity analysis showed clear separation between groups (PERMANOVA, p = 0.001, R² = 0.12)."
                ],
                "alpha_result": {"pvalue": 0.003, "metric": "Shannon", "direction": "lower", "group_name": "treatment"},
                "beta_result": {"pvalue": 0.001, "r2": 0.12, "distance_metric": "Bray-Curtis"}
            },
            "context": {"study_name": "Abx-Gut-2024", "journal_target": "Microbiome"}
        }
    """
    try:
        engine = _get_agent_engine()
        result = engine.write_paper_section(
            section_type=request.section_type,
            results_summary=request.results_summary,
            context=request.context,
        )
        return WritePaperResponse(**result)
    except Exception as e:
        logger.error(f"Paper writing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Paper writing failed: {str(e)}")


@router.post("/write-paper/full", response_model=FullPaperResponse)
async def write_full_paper(request: FullPaperRequest):
    """
    L5 – Generate a complete manuscript draft with all standard sections.

    Example:
        {
            "results_summary": {
                "title": "Gut microbiome shifts in antibiotic-treated mice",
                "n_samples": 48,
                "data_type": "16S rRNA amplicon",
                "study_design": "cross-sectional",
                "key_findings": [
                    "Shannon diversity was significantly reduced in the treatment group.",
                    "PERMANOVA revealed significant beta-diversity separation."
                ],
                "alpha_result": {"pvalue": 0.003, "metric": "Shannon", "direction": "lower", "group_name": "treatment"},
                "beta_result": {"pvalue": 0.001, "r2": 0.12, "distance_metric": "Bray-Curtis"},
                "differential_result": {"n_significant": 15, "top_feature": "Lactobacillus", "top_log2fc": -2.3, "top_adj_p": 0.001}
            },
            "context": {"study_name": "Abx-Gut-2024"}
        }
    """
    try:
        engine = _get_agent_engine()
        result = engine.write_full_paper(
            results_summary=request.results_summary,
            context=request.context,
        )
        return FullPaperResponse(**result)
    except Exception as e:
        logger.error(f"Full paper generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Full paper generation failed: {str(e)}")



# ── L4+ : Integrated Cross-Analysis Interpretation ─────────────────

class InterpretFullRequest(BaseModel):
    """L4+ – Request integrated interpretation across all analyses."""
    results: Dict[str, Any] = Field(..., description="Dictionary of all analysis results keyed by analysis name")
    metadata_summary: Optional[Dict[str, Any]] = Field(default=None, description="Optional session metadata (n_samples, groups, etc.)")
    question: Optional[str] = Field(default=None, description="User specific question for targeted interpretation")


class InterpretFullResponse(BaseModel):
    """L4+ – Integrated interpretation with knowledge base annotations."""
    integrated_narrative: str
    biological_context: List[str]
    caveats: List[str]
    follow_up_suggestions: List[str]
    contradictions: List[str]
    disease_relevance: List[Dict[str, Any]]
    llm_enhanced: bool = False
    llm_model: Optional[str] = None


@router.post("/interpret-full", response_model=InterpretFullResponse)
async def interpret_full(request: InterpretFullRequest):
    """
    L4+ – Generate a cross-analysis integrated interpretation.

    Unlike /interpret which handles one analysis at a time, this endpoint
    consumes ALL analysis results and produces a coherent narrative that:
    - Detects contradictions across analyses
    - Annotates significant taxa with biological context
    - Maps findings to known disease signatures
    - Suggests concrete follow-up analyses

    Example:
        {
            "results": {
                "alpha-diversity": {"result_data": {"group_statistics": {...}}},
                "permanova": {"result_data": {"pvalue": 0.02, "significant": true}},
                "lefse": {"result_data": {"n_significant": 12, "top_taxa": [...]}}
            },
            "metadata_summary": {"n_samples": 48, "n_groups": 2}
        }
    """
    try:
        engine = _get_agent_engine()
        result = engine.interpret_full_results(
            all_results=request.results,
            metadata_summary=request.metadata_summary,
            question=request.question,
        )
        return InterpretFullResponse(**result)
    except Exception as e:
        logger.error(f"Integrated interpretation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Integrated interpretation failed: {str(e)}")
