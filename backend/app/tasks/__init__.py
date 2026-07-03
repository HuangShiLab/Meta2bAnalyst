"""Meta2bAnalyst - Celery tasks module."""
from app.tasks.analysis_tasks import (
    alpha_diversity_task,
    beta_diversity_task,
    differential_task,
    pcoa_task,
    heatmap_task,
    random_forest_task,
    strain_composition_task,
    strain_differential_task,
    nmds_task,
    permanova_task,
    anosim_task,
)

__all__ = [
    "alpha_diversity_task",
    "beta_diversity_task",
    "differential_task",
    "pcoa_task",
    "heatmap_task",
    "random_forest_task",
    "strain_composition_task",
    "strain_differential_task",
    "nmds_task",
    "permanova_task",
    "anosim_task",
]
