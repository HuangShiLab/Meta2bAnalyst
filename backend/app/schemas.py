"""
Meta2bAnalyst - Pydantic Schemas (Request / Response Models)
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────── Session Schemas
class SessionCreate(BaseModel):
    """Request to create a new analysis session."""
    name: Optional[str] = None
    data_format: Optional[str] = None  # feature_table, biom, mothur, 2brad
    analysis_level: str = "species"  # species or strain
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SessionUpdate(BaseModel):
    """Request to update a session."""
    name: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None


class SessionResponse(BaseModel):
    """Session response model."""
    id: str
    created_at: datetime
    updated_at: datetime
    name: Optional[str] = None
    data_format: Optional[str] = None
    analysis_level: str
    status: str
    description: Optional[str] = None
    file_count: int = 0

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """List of sessions response."""
    sessions: List[SessionResponse]
    total: int


# ─────────────────────────────── Upload Schemas
class UploadResponse(BaseModel):
    """File upload response."""
    file_id: int
    session_id: str
    file_type: str
    original_name: str
    file_size: int
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    sample_count: Optional[int] = None
    feature_count: Optional[int] = None
    sample_names: Optional[List[str]] = None
    status: str
    message: str


class UploadListResponse(BaseModel):
    """List uploaded files for a session."""
    files: List[UploadResponse]


# ─────────────────────────────── Data Inspection Schemas
class DataInspectionResponse(BaseModel):
    """Data inspection response."""
    session_id: str
    file_id: int
    file_type: str
    row_count: int
    column_count: int
    sample_count: int
    feature_count: int
    sample_names: List[str]
    feature_names: List[str]
    summary: Dict[str, Any]
    preview: Optional[List[Dict[str, Any]]] = None


class FilterRequest(BaseModel):
    """Request to filter data."""
    min_samples: Optional[int] = Field(default=1, ge=1, description="Minimum samples a feature must appear in")
    min_abundance: Optional[float] = Field(default=0.0, ge=0.0, description="Minimum abundance threshold")
    max_features: Optional[int] = Field(default=None, ge=1, description="Maximum number of features to keep")
    sample_filter: Optional[List[str]] = Field(default=None, description="List of sample names to keep")
    feature_filter: Optional[List[str]] = Field(default=None, description="List of feature names to keep")

    @field_validator("max_features")
    def max_features_must_be_positive(cls, v):
        if v is not None and v < 1:
            raise ValueError("max_features must be at least 1")
        return v


class FilterResponse(BaseModel):
    """Filter response."""
    session_id: str
    row_count_before: int
    row_count_after: int
    column_count_before: int
    column_count_after: int
    samples_removed: int
    features_removed: int
    status: str


class NormalizeRequest(BaseModel):
    """Request to normalize data."""
    method: str = Field(default="relative", description="Normalization method: relative, css, tmm, tss, rarefaction")
    target_depth: Optional[int] = Field(default=None, ge=1, description="Rarefaction target depth")
    log_transform: bool = Field(default=False, description="Apply log transformation")

    @field_validator("method")
    def method_must_be_valid(cls, v):
        allowed = {"relative", "css", "tmm", "tss", "rarefaction", "none", "log", "clr", "log10"}
        if v not in allowed:
            raise ValueError(f"method must be one of {allowed}")
        return v


class NormalizeResponse(BaseModel):
    """Normalization response."""
    session_id: str
    method: str
    row_count: int
    column_count: int
    status: str
    message: str


# ─────────────────────────────── Analysis Schemas
class AnalysisRequest(BaseModel):
    """Request to run an analysis job."""
    analysis_type: str = Field(..., description="Analysis type: alpha, beta, differential, pcoa, nmds, heatmap, etc.")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Analysis-specific parameters")
    group_column: Optional[str] = Field(default=None, description="Metadata column for grouping")
    comparisons: Optional[List[str]] = Field(default=None, description="Groups to compare")

    @field_validator("analysis_type")
    def analysis_type_must_be_valid(cls, v):
        allowed = {
            "alpha", "beta", "differential", "pcoa", "nmds", "heatmap",
            "taxonomy_bar", "venn", "upset", "network", "correlation",
            "lefse", "ancom", "deseq2", "aldex2", "maaslin2", "random_forest",
            "permanova", "anosim",
        }
        if v not in allowed:
            raise ValueError(f"analysis_type must be one of {allowed}")
        return v


class AnalysisResponse(BaseModel):
    """Analysis job response."""
    job_id: int
    session_id: str
    job_type: str
    status: str
    parameters: Optional[Dict[str, Any]] = None
    result_path: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AnalysisResultResponse(BaseModel):
    """Analysis result response."""
    job_id: int
    status: str
    result_data: Optional[Dict[str, Any]] = None
    plot_data: Optional[Dict[str, Any]] = None
    download_url: Optional[str] = None


# ─────────────────────────────── Strain Analysis Schemas
class StrainAnalysisRequest(BaseModel):
    """Request for strain-level analysis."""
    species: str = Field(..., description="Target species for strain analysis")
    analysis_type: str = Field(default="strain_profile", description="Strain analysis type")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    min_ani: Optional[float] = Field(default=95.0, ge=0.0, le=100.0, description="Minimum ANI threshold")
    min_coverage: Optional[float] = Field(default=0.8, ge=0.0, le=1.0, description="Minimum coverage threshold")

    @field_validator("analysis_type")
    def strain_type_must_be_valid(cls, v):
        allowed = {"strain_profile", "strain_comparison", "ani_matrix", "phylogeny", "strain_pcoa"}
        if v not in allowed:
            raise ValueError(f"analysis_type must be one of {allowed}")
        return v


class StrainAnalysisResponse(BaseModel):
    """Strain analysis response."""
    job_id: int
    session_id: str
    species: str
    analysis_type: str
    status: str
    result_data: Optional[Dict[str, Any]] = None
    strain_count: Optional[int] = None
    message: Optional[str] = None


# ─────────────────────────────── Export Schemas
class ExportRequest(BaseModel):
    """Request to export data or results."""
    export_type: str = Field(..., description="Export type: data, result, plot, report")
    format: str = Field(default="csv", description="Export format: csv, tsv, xlsx, biom, json, pdf, png, svg, html")
    file_id: Optional[int] = Field(default=None, description="Specific file ID to export")
    job_id: Optional[int] = Field(default=None, description="Specific job ID to export")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @field_validator("export_type")
    def export_type_must_be_valid(cls, v):
        allowed = {"data", "result", "plot", "report", "metadata"}
        if v not in allowed:
            raise ValueError(f"export_type must be one of {allowed}")
        return v

    @field_validator("format")
    def format_must_be_valid(cls, v):
        allowed = {"csv", "tsv", "xlsx", "biom", "json", "pdf", "png", "svg", "html", "txt"}
        if v not in allowed:
            raise ValueError(f"format must be one of {allowed}")
        return v


class ExportResponse(BaseModel):
    """Export response."""
    export_id: str
    session_id: str
    export_type: str
    format: str
    file_path: str
    file_size: Optional[int] = None
    download_url: str
    status: str
    message: str


# ─────────────────────────────── Error Schemas
class ErrorResponse(BaseModel):
    """Error response model."""
    detail: str
    message: Optional[str] = None
    errors: Optional[List[Dict[str, Any]]] = None
