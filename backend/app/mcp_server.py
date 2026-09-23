"""Meta2bAnalyst MCP server.

Exposes the analysis platform as MCP tools, in the spirit of Paper2Agent
(Miao et al., Nature 2026, doi:10.1038/s41586-026-11044-y): instead of a
passive web UI, any MCP-compatible client (Claude Code, Kimi, Codex, ...) can
drive the full 56-module analysis pipeline through natural language.

Design: the tools are a thin loopback layer over our own REST API
(127.0.0.1:8000), so behaviour is byte-identical to what the frontend gets —
same validation, same engines, same error messages. A short-lived service
token is minted internally so uploads and session creation work even though
guests are read-only.

Mount: see app.main (mounted at /mcp).
"""
import base64
import logging
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import httpx
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

_API_BASE = os.environ.get("M2B_API_BASE", "http://127.0.0.1:8000/api/v1")
_SAMPLE_DATA_DIR = Path(os.environ.get("SAMPLE_DATA_DIR", "/app/sample_data"))
_JOB_POLL_TIMEOUT = int(os.environ.get("M2B_MCP_JOB_TIMEOUT", "600"))

mcp = FastMCP(
    "Meta2bAnalyst",
    instructions=(
        "Microbiome / metabolome / multi-omics analysis platform. Typical flow: "
        "load_demo_dataset(category) or create_session + upload_file, then "
        "run_analysis(session_id, analysis_type, parameters). Use "
        "list_analysis_modules() to discover analysis types and "
        "get_metadata_columns() to pick valid group_column values."
    ),
)

# Valid analysis_type values for run_analysis (REST path suffixes).
ANALYSIS_ENDPOINTS: Dict[str, str] = {
    # community structure
    "alpha-diversity": "Alpha diversity indices with group tests",
    "pcoa": "PCoA ordination (Bray-Curtis etc.)",
    "nmds": "NMDS ordination",
    "permanova": "PERMANOVA group effect test",
    "anosim": "ANOSIM group effect test",
    "rarefaction": "Rarefaction curves",
    "taxonomy-bar": "Taxonomy composition bar plot",
    "core-microbiome": "Core microbiome by prevalence/abundance",
    # differential & markers
    "differential": "Differential abundance (wilcoxon/ttest/lefse/ancombc/maaslin3 via parameters.test_method)",
    "lefse": "LEfSe LDA effect size",
    "volcano": "Volcano plot of differential results",
    "random-forest": "Random-forest group classifier + feature importance",
    # metabolomics
    "metabolomics": "Metabolomics analyses (analysis_type: pca | marker_discovery | ...)",
    # integration
    "cross-omics": "Cross-omics (analysis_type: procrustes | mantel | correlation)",
    "sparse-cca": "Sparse canonical correlation",
    "rda": "Redundancy analysis",
    "o2pls": "Two-way orthogonal PLS",
    "mofa": "MOFA+ factor analysis",
    "diablo": "mixOmics DIABLO integration",
    # networks & function
    "network": "Co-occurrence network",
    "correlation": "Feature correlation analysis",
    "pathway": "Pathway enrichment",
    "functional-prediction": "PICRUSt2/Tax4Fun functional prediction (requires reference DB)",
    # advanced
    "advanced-dimred": "t-SNE / UMAP embedding",
    "hierarchical-clustering": "Hierarchical clustering heatmap",
    "aldex2": "ALDEx2 differential (R)",
    "songbird": "Songbird multinomial regression",
    "wgcna": "WGCNA co-expression modules (R)",
    "enterotype": "Enterotype clustering",
    "source-tracking": "SourceTracker-like source attribution",
    # multi-site
    "multisite-pcoa": "Multi-site overlaid PCoA",
    "multisite-permanova": "Multi-site PERMANOVA (site + group effects)",
    "multisite-markers": "Site-specific marker discovery",
    "multisite-temporal": "Longitudinal trajectory (needs time column)",
    "multisite-network-compare": "Cross-site network comparison",
}

_DEMO_FILES: Dict[str, List[Dict[str, str]]] = {
    "microbiome": [
        {"name": "Matched_microbes_abd_261.tsv", "file_type": "microbiome", "dir": "microbiome"},
        {"name": "Matched_metadata_261.tsv", "file_type": "metadata", "dir": "microbiome"},
    ],
    "metabolome": [
        {"name": "Matched_metabolites_abd_261.txt", "file_type": "metabolome", "dir": "metabolome"},
        {"name": "Matched_metabolites_metadata_261.txt", "file_type": "metadata", "dir": "metabolome"},
    ],
    "multi-omics": [
        {"name": "Matched_microbes_abd_261.tsv", "file_type": "microbiome", "dir": "multi-omics"},
        {"name": "Matched_metabolites_abd_261.txt", "file_type": "metabolome", "dir": "multi-omics"},
        {"name": "Matched_metabolites_metadata_261.txt", "file_type": "metadata", "dir": "multi-omics"},
        {"name": "Matched_metadata_261.tsv", "file_type": "metadata", "dir": "multi-omics"},
    ],
    "multi-site-multi-omics": [
        {"name": "Urine_microbiome_GTDB_abd.txt", "file_type": "microbiome", "dir": "multi-site-multi-omics"},
        {"name": "Saliva_microbiome_GTDB_abd.txt", "file_type": "microbiome", "dir": "multi-site-multi-omics"},
        {"name": "metabolome_neg_urin_renamed.csv", "file_type": "metabolome", "dir": "multi-site-multi-omics"},
        {"name": "metabolome_pos_urin_renamed.csv", "file_type": "metabolome", "dir": "multi-site-multi-omics"},
        {"name": "metabolome_neg_saliva_renamed.csv", "file_type": "metabolome", "dir": "multi-site-multi-omics"},
        {"name": "metabolome_pos_saliva_renamed.csv", "file_type": "metabolome", "dir": "multi-site-multi-omics"},
        {"name": "Urine_metadata.txt", "file_type": "metadata", "dir": "multi-site-multi-omics"},
        {"name": "Saliva_metadata.txt", "file_type": "metadata", "dir": "multi-site-multi-omics"},
    ],
}


def _service_token() -> str:
    """Mint a short-lived admin token for loopback calls."""
    from app.database import SessionLocal
    from app.models import User
    from app.services.auth import create_token

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == "admin").first()
        if admin is not None:
            return create_token(admin)
        # DB not bootstrapped yet (tests): in-memory admin identity.
        return create_token(SimpleNamespace(id=0, username="mcp-service", role="admin"))
    finally:
        db.close()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=_API_BASE,
        headers={"Authorization": f"Bearer {_service_token()}"},
        timeout=httpx.Timeout(600.0, connect=10.0),
    )


def _check(resp: httpx.Response, what: str) -> Dict[str, Any]:
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:500]
        raise RuntimeError(f"{what} failed (HTTP {resp.status_code}): {detail}")
    return resp.json()


def _slim_result(result_data: Dict[str, Any], max_rows: int = 100) -> Dict[str, Any]:
    """Trim huge payloads for MCP transport: keep statistics, flag plots,
    cap table rows."""
    if not isinstance(result_data, dict):
        return result_data
    out: Dict[str, Any] = {}
    for key, value in result_data.items():
        if key == "plot_data":
            out["has_plot"] = bool(value)
            continue
        if isinstance(value, list) and len(value) > max_rows and value and isinstance(value[0], (dict, list)):
            out[key] = value[:max_rows]
            out[f"{key}_truncated"] = f"showing {max_rows}/{len(value)} rows"
            continue
        out[key] = value
    return out


async def _poll_job(client: httpx.AsyncClient, session_id: str, job_id: str) -> Dict[str, Any]:
    t0 = time.time()
    while time.time() - t0 < _JOB_POLL_TIMEOUT:
        resp = await client.get(f"/sessions/{session_id}/jobs/{job_id}/status")
        st = _check(resp, "get job status")
        status = st.get("status")
        if status in ("success", "completed"):
            r2 = await client.get(f"/sessions/{session_id}/jobs/{job_id}/result")
            return _check(r2, "get job result")
        if status in ("failed", "error"):
            raise RuntimeError(f"Analysis job failed: {st.get('error') or st}")
        await _sleep(3)
    raise RuntimeError(f"Analysis job {job_id} did not finish within {_JOB_POLL_TIMEOUT}s")


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


# ─────────────────────────────── Session tools


@mcp.tool
async def list_sessions() -> List[Dict[str, Any]]:
    """List analysis sessions visible on this Meta2bAnalyst server."""
    async with _client() as c:
        resp = await c.get("/sessions")
        data = _check(resp, "list sessions")
        return data.get("sessions", data)


@mcp.tool
async def create_session(name: str, description: str = "") -> Dict[str, Any]:
    """Create a new analysis session. Returns the session id used by all
    other tools."""
    async with _client() as c:
        resp = await c.post("/sessions", json={"name": name, "description": description})
        return _check(resp, "create session")


@mcp.tool
async def upload_file(
    session_id: str,
    file_type: str,
    filename: str,
    content_base64: str,
) -> Dict[str, Any]:
    """Upload a data file into a session.

    file_type: microbiome | metabolome | metadata | feature_table | biom |
    shared | taxonomy. content_base64 is the file content encoded in base64
    (read the local file and encode it). A single-omics session needs one
    feature table + one metadata file; multi-omics needs one feature table
    per omics plus metadata; multi-site needs one pair per body site.
    """
    content = base64.b64decode(content_base64)
    async with _client() as c:
        resp = await c.post(
            f"/sessions/{session_id}/upload",
            data={"file_type": file_type},
            files={"file": (filename, content, "application/octet-stream")},
        )
        return _check(resp, f"upload {filename}")


@mcp.tool
async def load_demo_dataset(category: str) -> Dict[str, Any]:
    """Create a session pre-loaded with a bundled demo dataset.

    category: microbiome | metabolome | multi-omics | multi-site-multi-omics
    (Huang mBio 2021 gingivitis cohort; multi-site is a saliva+urine cohort).
    Returns the new session id.
    """
    if category not in _DEMO_FILES:
        raise RuntimeError(f"Unknown demo category {category!r}; choose from {list(_DEMO_FILES)}")
    if not _SAMPLE_DATA_DIR.is_dir():
        raise RuntimeError(
            f"Sample data directory {_SAMPLE_DATA_DIR} is not available on the "
            "server; use create_session + upload_file with your own files."
        )
    async with _client() as c:
        resp = await c.post("/sessions", json={"name": f"MCP demo - {category}"})
        session = _check(resp, "create session")
        sid = session["id"]
        for f in _DEMO_FILES[category]:
            path = _SAMPLE_DATA_DIR / f["dir"] / f["name"]
            if not path.exists():
                raise RuntimeError(f"Demo file missing on server: {path}")
            resp = await c.post(
                f"/sessions/{sid}/upload",
                data={"file_type": f["file_type"]},
                files={"file": (f["name"], path.read_bytes(), "application/octet-stream")},
            )
            _check(resp, f"upload {f['name']}")
        return {"session_id": sid, "category": category, "files": len(_DEMO_FILES[category])}


@mcp.tool
async def list_session_files(session_id: str) -> Any:
    """List files uploaded to a session."""
    async with _client() as c:
        resp = await c.get(f"/sessions/{session_id}/files")
        return _check(resp, "list files")


@mcp.tool
async def get_metadata_columns(session_id: str) -> Any:
    """Get metadata columns (and, where available, their levels) for a
    session. Always call this before choosing a group_column."""
    async with _client() as c:
        resp = await c.get(f"/sessions/{session_id}/metadata/columns")
        if resp.status_code == 404:
            # Fall back to data inspection endpoint naming.
            resp = await c.get(f"/sessions/{session_id}/metadata")
        return _check(resp, "get metadata columns")


@mcp.tool
async def list_analysis_modules(category: Optional[str] = None) -> Any:
    """Discover registered analysis modules with descriptions, parameters and
    input requirements. Optionally filter by category: preprocessing |
    individual_omics | integration | marker | visualization."""
    from app.agent.module_registry import list_modules

    specs = list_modules(category)
    return [
        {
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "parameters": s.parameters,
            "input_requirements": s.input_requirements,
        }
        for s in specs
    ]


# ─────────────────────────────── Analysis tools


@mcp.tool
async def run_analysis(
    session_id: str,
    analysis_type: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run an analysis on a session and wait for the result.

    analysis_type is the REST endpoint name — see ANALYSIS_ENDPOINTS keys,
    e.g. "pcoa", "differential", "permanova", "metabolomics", "cross-omics",
    "multisite-pcoa". parameters is the request body, e.g.
    {"group_column": "Visit", "parameters": {"metric": "braycurtis"}}.
    Grouping always goes in top-level "group_column"; analysis-specific knobs
    go under "parameters". For differential with more than two groups, pass
    "comparisons": ["T1", "T9"].

    Large plot payloads are replaced by a has_plot flag; table data is capped
    at 100 rows (with data_truncated note).
    """
    if analysis_type not in ANALYSIS_ENDPOINTS:
        raise RuntimeError(
            f"Unknown analysis_type {analysis_type!r}. Valid: {sorted(ANALYSIS_ENDPOINTS)}"
        )
    payload = parameters or {}
    async with _client() as c:
        resp = await c.post(f"/sessions/{session_id}/analyze/{analysis_type}", json=payload)
        data = _check(resp, f"run {analysis_type}")
        status = data.get("status")
        if status in ("pending", "running"):
            data = await _poll_job(c, session_id, data["job_id"])
        result = data.get("result_data") or {}
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(f"{analysis_type} failed: {result['error']}")
        return {
            "job_id": data.get("job_id"),
            "analysis_type": analysis_type,
            "result": _slim_result(result),
        }


@mcp.tool
async def get_job_status(session_id: str, job_id: str) -> Any:
    """Check the status of a previously submitted analysis job."""
    async with _client() as c:
        resp = await c.get(f"/sessions/{session_id}/jobs/{job_id}/status")
        return _check(resp, "get job status")


# ─────────────────────────────── Knowledge base tools


@mcp.tool
async def search_knowledge_base(query: str, limit: int = 20) -> Any:
    """Search the built-in microbiome knowledge base (taxa, functions,
    disease associations). Use this to interpret marker taxa."""
    async with _client() as c:
        resp = await c.get("/agent/knowledge/search", params={"q": query, "limit": limit})
        return _check(resp, "search knowledge base")


@mcp.tool
async def list_paper_cards() -> Any:
    """List paper knowledge cards: one per PMID cited in the knowledge base,
    summarising each paper's contributed taxon-disease associations."""
    async with _client() as c:
        resp = await c.get("/agent/knowledge/paper-cards")
        return _check(resp, "list paper cards")


@mcp.tool
async def get_paper_card(pmid: str) -> Any:
    """Get the full knowledge card for one PMID: every taxon-disease
    association the knowledge base drew from that paper."""
    async with _client() as c:
        resp = await c.get(f"/agent/knowledge/paper-cards/{pmid}")
        return _check(resp, f"get paper card {pmid}")


def create_mcp_app():
    """Return the MCP ASGI app for mounting into FastAPI."""
    return mcp.http_app(path="/")
