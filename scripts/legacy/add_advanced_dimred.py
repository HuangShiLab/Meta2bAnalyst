import sys

path = sys.argv[1]

endpoint = '''

# ─────────────────────────────── Advanced Dimensionality Reduction (t-SNE / UMAP / MaAsLin3)

class AdvancedDimredRequest(BaseModel):
    method: str = 'both'
    tsne_perplexity: float = 30.0
    tsne_learning_rate: float = 200.0
    umap_n_neighbors: int = 15
    umap_min_dist: float = 0.1
    group_column: Optional[str] = None
    run_maaslin: bool = True
    fixed_effects: list = []
    random_effects: Optional[list] = None
    min_abundance: float = 0.0
    min_prevalence: float = 0.0


@router.post('/sessions/{session_id}/analyze/advanced-dimred', response_model=AnalysisResponse)
def advanced_dimred(
    session_id: str,
    request: AdvancedDimredRequest,
    db: DBSession = Depends(get_db),
):
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='advanced_dimred',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_advanced_dimred(df, metadata_df, request.model_dump())
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

with open(path, 'a') as f:
    f.write(endpoint)
print('Done')
