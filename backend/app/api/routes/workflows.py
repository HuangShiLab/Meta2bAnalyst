"""
Workflow Template Routes
========================
Named workflow persistence for the Workflow Builder: save the current DAG
under a name, list saved templates, load one back onto the canvas, delete
obsolete ones.

Templates are validated against MODULE_REGISTRY on save — a workflow that
references modules the platform cannot execute is rejected rather than
silently stored (the same honesty contract the planner enforces).
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.agent.module_registry import MODULE_REGISTRY
from app.database import get_db
from app.models import WorkflowTemplate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowSaveRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    plan: Dict[str, Any]
    layout: Optional[List[Dict[str, Any]]] = None


class WorkflowSummary(BaseModel):
    id: str
    name: str
    description: Optional[str]
    n_steps: int
    updated_at: Optional[str]


class WorkflowDetail(WorkflowSummary):
    plan: Dict[str, Any]
    layout: Optional[List[Dict[str, Any]]] = None


def _validate_plan(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the plan's steps, or raise 422 if the shape is unusable.

    A template that cannot be planned-and-executed later must not be saved:
    unknown module names, missing ids, or dangling dependencies are all
    rejected here.
    """
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise HTTPException(status_code=422, detail="plan.steps must be a non-empty list")

    ids = set()
    unknown = []
    for s in steps:
        if not isinstance(s, dict) or not s.get("id") or not s.get("module"):
            raise HTTPException(status_code=422, detail="each step needs 'id' and 'module'")
        ids.add(s["id"])
        if s["module"] not in MODULE_REGISTRY:
            unknown.append(s["module"])
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown modules not in registry: {sorted(set(unknown))}",
        )

    dangling = [
        (s["id"], dep)
        for s in steps
        for dep in (s.get("depends_on") or [])
        if dep not in ids
    ]
    if dangling:
        raise HTTPException(
            status_code=422,
            detail=f"dangling depends_on references: {dangling}",
        )
    return steps


def _to_summary(t: WorkflowTemplate) -> WorkflowSummary:
    return WorkflowSummary(
        id=t.id,
        name=t.name,
        description=t.description,
        n_steps=len((t.plan or {}).get("steps", [])),
        updated_at=t.updated_at.isoformat() if t.updated_at else None,
    )


@router.get("", response_model=List[WorkflowSummary])
def list_workflows(db: DBSession = Depends(get_db)):
    """List all saved workflow templates (without plan payloads)."""
    rows = db.query(WorkflowTemplate).order_by(WorkflowTemplate.updated_at.desc()).all()
    return [_to_summary(t) for t in rows]


@router.post("", response_model=WorkflowDetail)
def save_workflow(request: WorkflowSaveRequest, db: DBSession = Depends(get_db)):
    """Save (or overwrite, by name) a workflow template."""
    _validate_plan(request.plan)

    template = db.query(WorkflowTemplate).filter(WorkflowTemplate.name == request.name).first()
    if template is None:
        template = WorkflowTemplate(name=request.name)
        db.add(template)
    template.description = request.description
    template.plan = request.plan
    template.layout = request.layout
    db.commit()
    db.refresh(template)
    logger.info("Saved workflow template '%s' (%s)", template.name, template.id)
    return WorkflowDetail(**_to_summary(template).model_dump(), plan=template.plan, layout=template.layout)


@router.get("/{workflow_id}", response_model=WorkflowDetail)
def get_workflow(workflow_id: str, db: DBSession = Depends(get_db)):
    """Fetch one template including plan and layout."""
    template = db.get(WorkflowTemplate, workflow_id)
    if template is None:
        raise HTTPException(status_code=404, detail="workflow template not found")
    return WorkflowDetail(**_to_summary(template).model_dump(), plan=template.plan, layout=template.layout)


@router.delete("/{workflow_id}")
def delete_workflow(workflow_id: str, db: DBSession = Depends(get_db)):
    """Delete a template. Missing ids are a 404, not a silent success."""
    template = db.get(WorkflowTemplate, workflow_id)
    if template is None:
        raise HTTPException(status_code=404, detail="workflow template not found")
    db.delete(template)
    db.commit()
    return {"deleted": workflow_id}
