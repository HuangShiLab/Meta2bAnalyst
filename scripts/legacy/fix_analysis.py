import sys

path = sys.argv[1]
with open(path, 'r') as f:
    content = f.read()

# Fix 1: get_metadata_df - try CSV first, then TSV
old_metadata = """    try:
        df = pd.read_csv(data_file.file_path, sep='\\t', index_col=0)
        return df"""
new_metadata = """    try:
        try:
            df = pd.read_csv(data_file.file_path, index_col=0)
        except Exception:
            df = pd.read_csv(data_file.file_path, sep='\\t', index_col=0)
        return df"""
content = content.replace(old_metadata, new_metadata)

# Fix 2: Add imports for new wrapper functions
old_imports = """from app.services.analysis_engine import (
    AnalysisEngine,
    run_alpha_diversity,
    run_beta_diversity,
    run_differential_analysis,
    run_pcoa,
    run_nmds,
    run_heatmap,
    run_permanova,
    run_anosim,
    run_random_forest,
)"""
new_imports = """from app.services.analysis_engine import (
    AnalysisEngine,
    run_alpha_diversity,
    run_beta_diversity,
    run_differential_analysis,
    run_pcoa,
    run_nmds,
    run_heatmap,
    run_permanova,
    run_anosim,
    run_random_forest,
    run_network_analysis,
    run_correlation_analysis,
    run_pathway_analysis,
)"""
content = content.replace(old_imports, new_imports)

# Fix 3: Add legacy dispatch cases
old_dispatch = """        elif job.job_type == 'random_forest':
            result_data = run_random_forest(df, metadata_df, job.parameters)
        else:
            raise ValueError(f'Unknown analysis type: {job.job_type}')"""
new_dispatch = """        elif job.job_type == 'random_forest':
            result_data = run_random_forest(df, metadata_df, job.parameters)
        elif job.job_type == 'network':
            result_data = run_network_analysis(df, metadata_df, job.parameters)
        elif job.job_type == 'correlation':
            result_data = run_correlation_analysis(df, metadata_df, job.parameters)
        elif job.job_type == 'pathway':
            result_data = run_pathway_analysis(df, metadata_df, job.parameters)
        else:
            raise ValueError(f'Unknown analysis type: {job.job_type}')"""
content = content.replace(old_dispatch, new_dispatch)

# Fix 4: Add new endpoints at the end of the file
new_endpoints = '''

# ─────────────────────────────── Network Analysis

class NetworkAnalysisRequest(BaseModel):
    metric: str = 'sparcc'
    threshold: float = 0.3
    pvalue_threshold: float = 0.05
    n_permutations: int = 100
    top_n_features: int = 150


@router.post('/{session_id}/network', response_model=AnalysisResponse)
def network_analysis(
    session_id: str,
    request: NetworkAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    job = create_job(db, session_id, 'network', request.model_dump())
    df = _get_feature_df(session_id, db)
    result_data = run_network_analysis(df, parameters=request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Correlation Analysis

class CorrelationAnalysisRequest(BaseModel):
    target: str = 'feature'
    method: str = 'spearman'
    threshold: float = 0.3
    pvalue_threshold: float = 0.05
    group_column: Optional[str] = None


@router.post('/{session_id}/correlation', response_model=AnalysisResponse)
def correlation_analysis(
    session_id: str,
    request: CorrelationAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    job = create_job(db, session_id, 'correlation', request.model_dump())
    df = _get_feature_df(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    result_data = run_correlation_analysis(df, metadata_df, request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Pathway / Functional Analysis

class PathwayAnalysisRequest(BaseModel):
    method: str = 'hypergeometric'
    pvalue_threshold: float = 0.05
    min_count: int = 10
    group_column: Optional[str] = None


@router.post('/{session_id}/pathway', response_model=AnalysisResponse)
def pathway_analysis(
    session_id: str,
    request: PathwayAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    job = create_job(db, session_id, 'pathway', request.model_dump())
    df = _get_feature_df(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    result_data = run_pathway_analysis(df, metadata_df, request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )
'''

if 'class NetworkAnalysisRequest' not in content:
    content = content.rstrip() + '\n' + new_endpoints

with open(path, 'w') as f:
    f.write(content)

print('Done')
