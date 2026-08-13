"""
Meta2bAnalyst Agent Module
==========================
Intelligent analysis orchestration layer.

Provides:
- ModuleRegistry: Discovery of all available analysis modules
- AnalysisPlanner: Natural language → execution plan (DAG)
- WorkflowExecutor: Parallel DAG execution with streaming events
- ResultIntegrator: Multi-result combination into unified reports

Usage:
    from app.agent import get_planner, WorkflowExecutor, ResultIntegrator

    planner = get_planner()
    plan = await planner.plan("Find differential markers between Day 0 and Day 21")

    executor = WorkflowExecutor()
    executor.set_session_data(microbiome_df, metabolome_df, metadata_df)
    async for event in executor.execute(plan):
        print(event.to_dict())
"""
from app.agent.module_registry import (
    MODULE_REGISTRY,
    ModuleSpec,
    get_module_spec,
    list_modules,
    get_module_names,
)
from app.agent.planner import (
    AnalysisPlanner,
    ExecutionPlan,
    PlanStep,
    get_planner,
)
from app.agent.executor import (
    WorkflowExecutor,
    ExecutionEvent,
    run_agent_workflow,
)
from app.agent.integrator import (
    ResultIntegrator,
    ReportSection,
)

__all__ = [
    # Registry
    "MODULE_REGISTRY",
    "ModuleSpec",
    "get_module_spec",
    "list_modules",
    "get_module_names",
    # Planner
    "AnalysisPlanner",
    "ExecutionPlan",
    "PlanStep",
    "get_planner",
    # Executor
    "WorkflowExecutor",
    "ExecutionEvent",
    "run_agent_workflow",
    # Integrator
    "ResultIntegrator",
    "ReportSection",
]
