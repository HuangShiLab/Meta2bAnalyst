import sys

path = sys.argv[1]

endpoint = '''

# ─────────────────────────────── Source Tracking (FEAST-style)

class SourceTrackingRequest(BaseModel):
    sink_samples: list = []
    source_samples: list = []
    source_column: str = 'source_type'
    method: str = 'nnls'


@router.post('/sessions/{session_id}/analyze/source-tracking', response_model=AnalysisResponse)
def source_tracking(
    session_id: str,
    request: SourceTrackingRequest,
    db: DBSession = Depends(get_db),
):
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='source_tracking',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_source_tracking_analysis(df, metadata_df, request.model_dump())
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
