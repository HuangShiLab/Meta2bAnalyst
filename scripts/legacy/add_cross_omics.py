import sys

path = sys.argv[1]

endpoint = '''

# ─────────────────────────────── Cross-omics Analysis (Procrustes + Mantel)

class CrossOmicsRequest(BaseModel):
    procrustes_method: str = 'pcoa'
    mantel_metric: str = 'braycurtis'
    mantel_method: str = 'pearson'
    n_permutations: int = 999
    group_column: Optional[str] = None


@router.post('/sessions/{session_id}/analyze/cross-omics', response_model=AnalysisResponse)
def cross_omics_analysis(
    session_id: str,
    request: CrossOmicsRequest,
    db: DBSession = Depends(get_db),
):
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='cross_omics',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_cross_omics_analysis(df, None, metadata_df, request.model_dump())
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
