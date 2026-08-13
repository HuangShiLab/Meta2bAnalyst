"""
Agent Module Registry
=====================
Registers all available analysis modules with their metadata,
parameters, constraints, and I/O specifications.
This registry enables the Agent Planner to discover and compose
analysis workflows dynamically.
"""
from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass, field


@dataclass
class ModuleSpec:
    """Specification for a single analysis module."""
    name: str
    description: str
    category: str  # 'preprocessing', 'individual_omics', 'integration', 'marker', 'visualization'
    input_requirements: Dict[str, Any]
    parameters: Dict[str, Any]
    output_spec: Dict[str, str]
    constraints: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)  # module names that should typically precede this


# ───────────────────────────────────────────────────────────────
# MODULE REGISTRY
# ───────────────────────────────────────────────────────────────

MODULE_REGISTRY: Dict[str, ModuleSpec] = {
    # ── Data Validation ─────────────────────────────────────────
    "data_validator": ModuleSpec(
        name="data_validator",
        description="Validate data format, check dimensions, detect missing values, verify sample-metabolite alignment",
        category="preprocessing",
        input_requirements={"microbiome": "optional", "metabolome": "optional", "metadata": "optional"},
        parameters={},
        output_spec={"report": "dict", "valid": "bool"},
        constraints=["Must run before any analysis module"],
    ),

    # ── Individual Omics: Microbiome ────────────────────────────
    "microbiome_pcoa": ModuleSpec(
        name="microbiome_pcoa",
        description="Principal Coordinate Analysis of microbiome composition using Bray-Curtis or UniFrac distances",
        category="individual_omics",
        input_requirements={"microbiome": "required", "metadata": "optional"},
        parameters={
            "distance_metric": {"type": "enum", "options": ["braycurtis", "unweighted_unifrac", "weighted_unifrac"], "default": "braycurtis"},
            "ordination_method": {"type": "enum", "options": ["pcoa", "nmds"], "default": "pcoa"},
            "group_column": {"type": "string", "default": "Visit"},
        },
        output_spec={"plot_data": "plotly", "coordinates": "dataframe", "eigenvalues": "array"},
        constraints=["Requires microbiome count/abundance matrix (samples × taxa)"],
    ),

    "microbiome_alpha": ModuleSpec(
        name="microbiome_alpha",
        description="Alpha diversity analysis for microbiome (richness, Shannon, Simpson, Pielou, inverse Simpson)",
        category="individual_omics",
        input_requirements={"microbiome": "required", "metadata": "optional"},
        parameters={
            "metrics": {"type": "array", "options": ["richness", "shannon", "simpson", "pielou", "inverse_simpson"], "default": ["shannon", "simpson"]},
            "group_column": {"type": "string", "default": "Visit"},
        },
        output_spec={"plot_data": "plotly", "diversity_table": "dataframe"},
    ),

    "microbiome_nmds": ModuleSpec(
        name="microbiome_nmds",
        description="Non-metric Multidimensional Scaling for microbiome community structure",
        category="individual_omics",
        input_requirements={"microbiome": "required", "metadata": "optional"},
        parameters={
            "distance_metric": {"type": "enum", "options": ["braycurtis", "jaccard"], "default": "braycurtis"},
            "n_components": {"type": "int", "default": 2, "range": [2, 3]},
            "group_column": {"type": "string", "default": "Visit"},
        },
        output_spec={"plot_data": "plotly", "stress": "float"},
    ),

    # ── Individual Omics: Metabolome ────────────────────────────
    "metabolome_pca": ModuleSpec(
        name="metabolome_pca",
        description="Principal Component Analysis of metabolite intensities with z-score, log, or CLR transformation",
        category="individual_omics",
        input_requirements={"metabolome": "required", "metadata": "optional"},
        parameters={
            "transformation": {"type": "enum", "options": ["zscore", "log", "log1p", "clr", "none"], "default": "zscore"},
            "n_components": {"type": "int", "default": 10, "range": [2, 50]},
            "group_column": {"type": "string", "default": "Visit"},
        },
        output_spec={"plot_data": "plotly", "explained_variance": "array", "loadings": "dataframe"},
        constraints=["zscore recommended for most metabolomics data"],
    ),

    "metabolome_alpha": ModuleSpec(
        name="metabolome_alpha",
        description="Alpha diversity analysis for metabolome (metabolite richness, Shannon, Simpson, Pielou)",
        category="individual_omics",
        input_requirements={"metabolome": "required", "metadata": "optional"},
        parameters={
            "metrics": {"type": "array", "options": ["richness", "shannon", "simpson", "pielou", "inverse_simpson"], "default": ["richness", "shannon"]},
            "group_column": {"type": "string", "default": "Visit"},
        },
        output_spec={"plot_data": "plotly", "diversity_table": "dataframe"},
    ),

    # ── Statistical Testing ─────────────────────────────────────
    "permanova": ModuleSpec(
        name="permanova",
        description="Permutational Multivariate Analysis of Variance to test metadata effects on community/metabolic composition",
        category="individual_omics",
        input_requirements={"data": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "default": "Visit"},
            "distance_metric": {"type": "enum", "options": ["braycurtis", "euclidean"], "default": "braycurtis"},
            "permutations": {"type": "int", "default": 999},
            "data_type": {"type": "enum", "options": ["microbiome", "metabolome"], "default": "microbiome"},
        },
        output_spec={"statistics": "dict", "significant_variables": "list"},
        constraints=["Requires both data matrix and metadata with grouping variable"],
    ),

    # ── Marker Discovery ────────────────────────────────────────
    "microbiome_marker": ModuleSpec(
        name="microbiome_marker",
        description="Differential abundance analysis for microbiome using CLR transformation + Wilcoxon rank-sum test (compositionally appropriate)",
        category="marker",
        input_requirements={"microbiome": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "default": "Visit"},
            "reference_group": {"type": "string", "default": "T4"},
            "transformation": {"type": "enum", "options": ["clr"], "default": "clr"},
            "test_method": {"type": "enum", "options": ["mannwhitney"], "default": "mannwhitney"},
            "pvalue_threshold": {"type": "float", "default": 0.05, "range": [0.001, 0.1]},
            "fc_threshold": {"type": "float", "default": 1.5, "range": [1.2, 4.0]},
        },
        output_spec={"volcano_plot": "plotly", "significant_features": "dataframe", "statistics": "dict"},
        constraints=[
            "MUST use CLR transformation for compositional microbiome data",
            "MUST use Wilcoxon rank-sum (Mann-Whitney U) test - t-test is inappropriate for compositional data",
            "Reference group must exist in the grouping variable",
        ],
    ),

    "metabolome_marker": ModuleSpec(
        name="metabolome_marker",
        description="Differential metabolite analysis using log1p transformation + Welch t-test",
        category="marker",
        input_requirements={"metabolome": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "default": "Visit"},
            "reference_group": {"type": "string", "default": "T4"},
            "transformation": {"type": "enum", "options": ["log1p", "log", "zscore"], "default": "log1p"},
            "test_method": {"type": "enum", "options": ["welch", "ttest", "mannwhitney"], "default": "welch"},
            "pvalue_threshold": {"type": "float", "default": 0.05, "range": [0.001, 0.1]},
            "fc_threshold": {"type": "float", "default": 1.5, "range": [1.2, 4.0]},
        },
        output_spec={"volcano_plot": "plotly", "significant_features": "dataframe", "statistics": "dict"},
        constraints=["log1p + Welch t-test recommended for metabolomics intensity data"],
    ),

    # ── Multi-omics Integration ─────────────────────────────────
    "procrustes": ModuleSpec(
        name="procrustes",
        description="Procrustes analysis to align and compare microbiome and metabolome ordinations",
        category="integration",
        input_requirements={"microbiome": "required", "metabolome": "required", "metadata": "optional"},
        parameters={
            "group_column": {"type": "string", "default": "Visit"},
            "microbiome_ordination": {"type": "enum", "options": ["pcoa"], "default": "pcoa"},
            "metabolome_ordination": {"type": "enum", "options": ["pca"], "default": "pca"},
        },
        output_spec={"plot_data": "plotly", "m12": "float", "scale": "float", "correlation": "float"},
        constraints=["Requires both microbiome and metabolome data"],
        depends_on=["microbiome_pcoa", "metabolome_pca"],
    ),

    "mantel_test": ModuleSpec(
        name="mantel_test",
        description="Mantel test to correlate microbiome and metabolome distance matrices",
        category="integration",
        input_requirements={"microbiome": "required", "metabolome": "required"},
        parameters={
            "microbiome_metric": {"type": "enum", "options": ["braycurtis"], "default": "braycurtis"},
            "metabolome_metric": {"type": "enum", "options": ["braycurtis", "euclidean"], "default": "braycurtis"},
            "permutations": {"type": "int", "default": 999},
        },
        output_spec={"correlation": "float", "pvalue": "float", "plot_data": "plotly"},
        constraints=["More robust than Procrustes - does not require dimensionality reduction"],
        depends_on=[],
    ),

    "sparse_cca": ModuleSpec(
        name="sparse_cca",
        description="Sparse Canonical Correlation Analysis to find sparse linear combinations of taxa and metabolites maximizing cross-correlation",
        category="integration",
        input_requirements={"microbiome": "required", "metabolome": "required"},
        parameters={
            "n_components": {"type": "int", "default": 2, "range": [1, 5]},
            "sparsity_x": {"type": "float", "default": 0.3, "range": [0.0, 1.0]},
            "sparsity_y": {"type": "float", "default": 0.3, "range": [0.0, 1.0]},
        },
        output_spec={"plot_data": "plotly", "correlations": "array", "loadings": "dict"},
    ),

    "rda": ModuleSpec(
        name="rda",
        description="Redundancy Analysis to model metabolome as a linear function of microbiome composition",
        category="integration",
        input_requirements={"microbiome": "required", "metabolome": "required"},
        parameters={
            "n_components": {"type": "int", "default": 2, "range": [1, 5]},
            "scale": {"type": "bool", "default": True},
        },
        output_spec={"plot_data": "plotly", "constrained_variance": "float", "pseudo_f": "float"},
    ),

    "o2pls": ModuleSpec(
        name="o2pls",
        description="O2PLS to separate joint variation (shared) from orthogonal variation (unique to each omics) and residual noise",
        category="integration",
        input_requirements={"microbiome": "required", "metabolome": "required"},
        parameters={
            "n_joint": {"type": "int", "default": 2, "range": [1, 5]},
            "n_ortho_x": {"type": "int", "default": 1, "range": [0, 3]},
            "n_ortho_y": {"type": "int", "default": 1, "range": [0, 3]},
        },
        output_spec={"plot_data": "plotly", "joint_variance_x": "float", "joint_variance_y": "float"},
    ),

    "cross_correlation": ModuleSpec(
        name="cross_correlation",
        description="Spearman rank correlation between bacterial genera and metabolites",
        category="integration",
        input_requirements={"microbiome": "required", "metabolome": "required", "metadata": "optional"},
        parameters={
            "method": {"type": "enum", "options": ["spearman", "pearson"], "default": "spearman"},
            "top_n_genera": {"type": "int", "default": 15, "range": [5, 50]},
            "top_n_metabolites": {"type": "int", "default": 20, "range": [5, 100]},
        },
        output_spec={"heatmap": "plotly", "significant_pairs": "dataframe", "correlation_matrix": "dataframe"},
    ),

    # ── Network Analysis ────────────────────────────────────────
    "network_sparcc": ModuleSpec(
        name="network_sparcc",
        description="SparCC correlation network for microbiome taxa, accounting for compositional effects",
        category="individual_omics",
        input_requirements={"microbiome": "required"},
        parameters={
            "threshold": {"type": "float", "default": 0.3, "range": [0.1, 0.8]},
            "permutations": {"type": "int", "default": 100},
        },
        output_spec={"network_data": "dict", "adjacency_matrix": "dataframe"},
    ),

    # ── Functional Analysis ─────────────────────────────────────
    "pathway_kegg": ModuleSpec(
        name="pathway_kegg",
        description="KEGG pathway enrichment analysis for differentially abundant features",
        category="individual_omics",
        input_requirements={"features": "required"},
        parameters={
            "pathway_db": {"type": "enum", "options": ["KEGG", "MetaCyc"], "default": "KEGG"},
            "pvalue_threshold": {"type": "float", "default": 0.05},
        },
        output_spec={"enrichment_table": "dataframe", "plot_data": "plotly"},
    ),

    "functional_prediction": ModuleSpec(
        name="functional_prediction",
        description="PICRUSt2 functional prediction from 16S rRNA gene sequencing data",
        category="individual_omics",
        input_requirements={"microbiome": "required"},
        parameters={
            "database": {"type": "enum", "options": ["KEGG", "COG", "EC"], "default": "KEGG"},
        },
        output_spec={"function_table": "dataframe", "pathway_abundance": "dataframe"},
    ),

    # ── Advanced Methods ────────────────────────────────────────
    "tsne": ModuleSpec(
        name="tsne",
        description="t-SNE dimensionality reduction for visualization",
        category="individual_omics",
        input_requirements={"data": "required"},
        parameters={
            "n_components": {"type": "int", "default": 2, "options": [2, 3]},
            "perplexity": {"type": "float", "default": 30.0, "range": [5, 100]},
            "data_type": {"type": "enum", "options": ["microbiome", "metabolome"], "default": "microbiome"},
        },
        output_spec={"plot_data": "plotly", "embeddings": "dataframe"},
    ),

    "umap": ModuleSpec(
        name="umap",
        description="UMAP dimensionality reduction for visualization",
        category="individual_omics",
        input_requirements={"data": "required"},
        parameters={
            "n_components": {"type": "int", "default": 2, "options": [2, 3]},
            "n_neighbors": {"type": "int", "default": 15, "range": [2, 100]},
            "min_dist": {"type": "float", "default": 0.1, "range": [0.0, 1.0]},
            "data_type": {"type": "enum", "options": ["microbiome", "metabolome"], "default": "microbiome"},
        },
        output_spec={"plot_data": "plotly", "embeddings": "dataframe"},
    ),

    "maaslin3": ModuleSpec(
        name="maaslin3",
        description="MaAsLin3 multivariate association analysis with mixed-effects models",
        category="marker",
        input_requirements={"microbiome": "required", "metadata": "required"},
        parameters={
            "fixed_effects": {"type": "array", "default": ["Visit"]},
            "random_effects": {"type": "array", "default": []},
            "normalization": {"type": "enum", "options": ["TSS", "CLR", "NONE"], "default": "TSS"},
        },
        output_spec={"significant_associations": "dataframe", "volcano_plot": "plotly"},
    ),

    # ── Report Generation ───────────────────────────────────────
    "report_generator": ModuleSpec(
        name="report_generator",
        description="Combine all analysis results into a unified PDF or HTML report with figures and tables",
        category="visualization",
        input_requirements={"results": "required"},
        parameters={
            "format": {"type": "enum", "options": ["pdf", "html", "markdown"], "default": "pdf"},
            "title": {"type": "string", "default": "Multi-omics Analysis Report"},
            "include_methods": {"type": "bool", "default": True},
        },
        output_spec={"report_path": "string", "report_url": "string"},
        depends_on=[],
    ),
}


def get_module_spec(name: str) -> Optional[ModuleSpec]:
    """Get module specification by name."""
    return MODULE_REGISTRY.get(name)


def list_modules(category: Optional[str] = None) -> List[ModuleSpec]:
    """List all modules, optionally filtered by category."""
    if category:
        return [m for m in MODULE_REGISTRY.values() if m.category == category]
    return list(MODULE_REGISTRY.values())


def get_module_names() -> List[str]:
    """Get all registered module names."""
    return list(MODULE_REGISTRY.keys())
