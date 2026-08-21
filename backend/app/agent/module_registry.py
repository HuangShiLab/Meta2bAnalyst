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
# REGISTRATION CONTRACT
# ───────────────────────────────────────────────────────────────
#
# A module is only usable by the Agent when it has BOTH:
#   1. a ModuleSpec in MODULE_REGISTRY (below), and
#   2. an entry in app.agent.executor._MODULE_FUNCTIONS.
#
# Registering a spec without the executor mapping produces plans whose steps
# die with "Unknown module" at run time, which is worse than not offering the
# module at all (tests/test_agent_executor.py::test_all_modules_have_functions
# guards this). app.agent.planner.MODULE_KEYWORDS can therefore route to more
# names than are registered; the planner tells the user those are unavailable
# rather than emitting an unrunnable step
# (see planner.unregistered_keyword_modules()).
#
# PENDING_EXECUTOR_WIRING lists the keyword-routable modules that already have
# a real service behind them and are waiting only on the executor mapping.
# Add the executor entry FIRST, then move the module into MODULE_REGISTRY.
#
# 2026-08-15: all previously pending modules (aldex2, anosim, diablo,
# enterotype, heatmap, mofa, random_forest, rarefaction, songbird,
# source_tracking, strain_analyzer, taxonomy_bar, unifrac, upset, volcano,
# wgcna) are now wired in executor._MODULE_FUNCTIONS and registered below.
# 'upset' required a new service (app.services.upset_plot); 'volcano' is a
# plot view over microbiome marker discovery. Keep this list empty.
PENDING_EXECUTOR_WIRING: Dict[str, str] = {}


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

    "normalization": ModuleSpec(
        name="normalization",
        description="Unified normalization entry: TSS/CSS/CLR/ILR/TMM/Rarefaction for microbiome; z-score/Pareto/Quantile/Sum/log1p for metabolome",
        category="preprocessing",
        input_requirements={"data": "required"},
        parameters={
            "data_type": {"type": "enum", "options": ["microbiome", "metabolome"]},
            "method": {"type": "enum", "options": ["tss", "css", "clr", "ilr", "tmm", "rarefaction", "none", "zscore", "pareto", "quantile", "sum", "log1p"]},
            "reference_samples": {"type": "array", "default": None},
        },
        output_spec={"normalized_matrix": "dataframe", "scaling_factors": "dict", "plot_data": "plotly"},
        constraints=["Must run before any analysis that requires standardized data"],
    ),

    "outlier_detection": ModuleSpec(
        name="outlier_detection",
        description="Aitchison distance / Mahalanobis PCA / Isolation Forest / Cook's distance outlier detection",
        category="preprocessing",
        input_requirements={"data": "required", "metadata": "optional"},
        parameters={
            "method": {"type": "enum", "options": ["aitchison", "mahalanobis_pca", "isolation_forest", "cooks_distance"], "default": "aitchison"},
            "group_column": {"type": "string", "default": None},
            "threshold": {"type": "float", "default": 0.05},
        },
        output_spec={"outlier_flags": "dataframe", "plot_data": "plotly", "report": "dict"},
    ),
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

    # ── Cross-site / cross-omics (Zhang et al., Microbiome 2026) ──────────

    "cross_site_permanova": ModuleSpec(
        name="cross_site_permanova",
        description="Distance-based variance estimation: per-site microbiome explanatory power (cumulative R2) over a target omics layer, via univariate feature PERMANOVA screen + multivariable model (adonis2-style)",
        category="integration",
        input_requirements={"microbiome": "required", "metabolome": "required", "metadata": "required"},
        parameters={
            "site_column": {"type": "string", "default": None, "description": "Metadata column with body site (auto-detected if omitted)"},
            "subject_column": {"type": "string", "default": None, "description": "Metadata column with subject id (auto-detected if omitted)"},
            "p_threshold": {"type": "float", "default": 0.05},
            "n_permutations": {"type": "int", "default": 999},
            "max_features_per_site": {"type": "int", "default": 200},
        },
        output_spec={"sites": "dict of per-site cumulative_r2 + per-feature results"},
        constraints=["Longitudinal repeats are collapsed to per-subject means before testing"],
        depends_on=[],
    ),

    "cross_omics_gbdt": ModuleSpec(
        name="cross_omics_gbdt",
        description="Per-target GBDT/LASSO predictive screen with nested CV, in-fold Spearman feature pre-selection, bootstrap R2 distribution with 95% CI and feature reproducibility - identifies which microbial features carry cross-omics associations",
        category="integration",
        input_requirements={"microbiome": "required", "metabolome": "required"},
        parameters={
            "method": {"type": "enum", "options": ["gbdt", "lasso"], "default": "gbdt"},
            "site": {"type": "string", "default": None, "description": "Restrict predictors to one body site"},
            "r_threshold": {"type": "float", "default": 0.3},
            "p_threshold": {"type": "float", "default": 0.05},
            "n_bootstrap": {"type": "int", "default": 20},
            "cv_folds": {"type": "int", "default": 5},
        },
        output_spec={"results": "per-target mean_r2, ci95, t_padj, top_features with reproducibility"},
        constraints=["Feature selection happens inside each training fold - no leakage"],
        depends_on=[],
    ),

    "cross_site_network": ModuleSpec(
        name="cross_site_network",
        description="Spearman correlation network between each body site's features and target omics features, with hub detection (degree/betweenness) and shared-target identification across sites",
        category="integration",
        input_requirements={"microbiome": "required", "metabolome": "required", "metadata": "required"},
        parameters={
            "r_threshold": {"type": "float", "default": 0.3},
            "p_threshold": {"type": "float", "default": 0.05},
            "top_hubs": {"type": "int", "default": 5},
        },
        output_spec={"site_hubs": "dict", "shared_targets": "list", "n_edges": "int"},
        constraints=["FDR correction applied within each site"],
        depends_on=[],
    ),

    "cross_site_concordance": ModuleSpec(
        name="cross_site_concordance",
        description="Find features disease-associated in the SAME direction across multiple body sites/omics layers (per-layer Mann-Whitney + FDR, concordance = significant in >= min_sites layers with same sign)",
        category="integration",
        input_requirements={"microbiome": "required", "metadata": "required", "metabolome": "optional"},
        parameters={
            "group_column": {"type": "string", "required": True, "description": "Two-level metadata column (e.g. disease status)"},
            "min_sites": {"type": "int", "default": 2},
            "p_threshold": {"type": "float", "default": 0.05},
        },
        output_spec={"concordant_features": "list with layers, directions, concordant_direction flag"},
        constraints=["Requires exactly two groups in group_column"],
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

    # ── Community Statistics & ML ───────────────────────────────
    "anosim": ModuleSpec(
        name="anosim",
        description="Analysis of Similarities to test whether groups differ in community composition",
        category="individual_omics",
        input_requirements={"microbiome": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "default": "Visit"},
            "distance_metric": {"type": "enum", "options": ["braycurtis", "jaccard"], "default": "braycurtis"},
            "n_permutations": {"type": "int", "default": 999},
        },
        output_spec={"statistics": "dict", "r_statistic": "float", "pvalue": "float"},
        constraints=["Requires metadata with at least 2 groups"],
    ),

    "random_forest": ModuleSpec(
        name="random_forest",
        description="Random Forest classification with feature importance to identify discriminative taxa/features",
        category="marker",
        input_requirements={"microbiome": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "default": "Visit"},
            "n_estimators": {"type": "int", "default": 500, "range": [50, 2000]},
        },
        output_spec={"feature_importance": "dataframe", "accuracy": "float", "plot_data": "plotly"},
        constraints=["Requires metadata with a grouping variable"],
    ),

    "aldex2": ModuleSpec(
        name="aldex2",
        description="ALDEx2-style differential abundance: CLR transform + Welch t-test / Mann-Whitney / Kruskal-Wallis with effect sizes",
        category="marker",
        input_requirements={"microbiome": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "default": "Visit"},
            "test_method": {"type": "enum", "options": ["welch", "mannwhitney", "kruskal"], "default": "welch"},
            "effect_threshold": {"type": "float", "default": 1.0},
            "pvalue_threshold": {"type": "float", "default": 0.05},
        },
        output_spec={"volcano_plot": "plotly", "significant_features": "dataframe", "statistics": "dict"},
    ),

    "songbird": ModuleSpec(
        name="songbird",
        description="Songbird-style multinomial regression differential abundance with rank-based feature comparisons",
        category="marker",
        input_requirements={"microbiome": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "default": "Visit"},
            "epochs": {"type": "int", "default": 1000},
            "top_n": {"type": "int", "default": 50},
        },
        output_spec={"rankings": "dataframe", "plot_data": "plotly", "statistics": "dict"},
    ),

    "enterotype": ModuleSpec(
        name="enterotype",
        description="Enterotype clustering (PAM/K-means on Jaccard or Bray-Curtis distances) with PCoA visualisation",
        category="individual_omics",
        input_requirements={"microbiome": "required", "metadata": "optional"},
        parameters={
            "n_clusters": {"type": "int", "default": 3, "range": [2, 10]},
            "distance_metric": {"type": "enum", "options": ["jaccard", "braycurtis"], "default": "jaccard"},
            "clustering_method": {"type": "enum", "options": ["pam", "kmeans", "auto"], "default": "pam"},
            "group_column": {"type": "string", "default": "Visit"},
        },
        output_spec={"plot_data": "plotly", "cluster_assignments": "dataframe", "statistics": "dict"},
    ),

    # ── Visualisation ───────────────────────────────────────────
    "rarefaction": ModuleSpec(
        name="rarefaction",
        description="Rarefaction curves to assess sequencing depth sufficiency per sample or group",
        category="visualization",
        input_requirements={"microbiome": "required", "metadata": "optional"},
        parameters={
            "group_column": {"type": "string", "default": None},
            "metrics": {"type": "array", "default": ["observed", "shannon"]},
            "max_depth": {"type": "int", "default": None},
            "steps": {"type": "int", "default": 20},
            "iterations": {"type": "int", "default": 10},
        },
        output_spec={"plot_data": "plotly", "curves": "dataframe"},
    ),

    "taxonomy_bar": ModuleSpec(
        name="taxonomy_bar",
        description="Stacked bar chart of community composition at phylum/genus/species level",
        category="visualization",
        input_requirements={"microbiome": "required", "metadata": "optional"},
        parameters={
            "group_column": {"type": "string", "default": None},
            "tax_level": {"type": "enum", "options": ["phylum", "genus", "species"], "default": "genus"},
            "top_n": {"type": "int", "default": 15, "range": [5, 50]},
        },
        output_spec={"plot_data": "plotly", "composition_table": "dataframe"},
    ),

    "heatmap": ModuleSpec(
        name="heatmap",
        description="Clustered heatmap of the top variable features across samples",
        category="visualization",
        input_requirements={"microbiome": "required", "metadata": "optional"},
        parameters={
            "top_n": {"type": "int", "default": 50, "range": [10, 200]},
            "normalize": {"type": "enum", "options": ["zscore", "log", "none"], "default": "zscore"},
            "group_column": {"type": "string", "default": None},
        },
        output_spec={"plot_data": "plotly"},
    ),

    "volcano": ModuleSpec(
        name="volcano",
        description="Volcano plot of differential abundance (effect size vs significance) from marker discovery",
        category="visualization",
        input_requirements={"microbiome": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "default": "Visit"},
            "reference_group": {"type": "string", "default": "T4"},
            "pvalue_threshold": {"type": "float", "default": 0.05},
            "fc_threshold": {"type": "float", "default": 1.5},
        },
        output_spec={"plot_data": "plotly", "significant_features": "dataframe"},
        depends_on=[],
    ),

    "upset": ModuleSpec(
        name="upset",
        description="UpSet plot of feature-set intersections across groups (shared vs group-specific prevalent features)",
        category="visualization",
        input_requirements={"microbiome": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "default": "Visit"},
            "prevalence_threshold": {"type": "float", "default": 0.25, "range": [0.0, 1.0]},
            "top_n": {"type": "int", "default": 20},
        },
        output_spec={"plot_data": "plotly", "intersections": "dataframe", "set_sizes": "dict"},
    ),

    # ── Integration (additional) ────────────────────────────────
    "mofa": ModuleSpec(
        name="mofa",
        description="MOFA+ style multi-omics factor analysis extracting latent factors shared across microbiome and metabolome",
        category="integration",
        input_requirements={"microbiome": "required", "metabolome": "required", "metadata": "optional"},
        parameters={
            "n_factors": {"type": "int", "default": 5, "range": [2, 15]},
            "group_column": {"type": "string", "default": "Visit"},
        },
        output_spec={"plot_data": "plotly", "factors": "dataframe", "variance_explained": "dict"},
    ),

    "diablo": ModuleSpec(
        name="diablo",
        description="DIABLO-style supervised integration (sparse PLS-DA) discriminating groups from combined omics blocks",
        category="integration",
        input_requirements={"microbiome": "required", "metabolome": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "default": "Visit"},
            "n_components": {"type": "int", "default": 2, "range": [2, 5]},
        },
        output_spec={"plot_data": "plotly", "loadings": "dict", "classification": "dict"},
    ),

    # ── Network / Phylogenetic / Strain / Source ────────────────
    "wgcna": ModuleSpec(
        name="wgcna",
        description="WGCNA-style co-occurrence module detection with module-trait correlation",
        category="individual_omics",
        input_requirements={"microbiome": "required", "metadata": "optional"},
        parameters={
            "power": {"type": "int", "default": 6, "range": [1, 20]},
            "min_module_size": {"type": "int", "default": 10},
            "merge_cut_height": {"type": "float", "default": 0.25},
        },
        output_spec={"plot_data": "plotly", "modules": "dataframe", "statistics": "dict"},
    ),

    "unifrac": ModuleSpec(
        name="unifrac",
        description="UniFrac phylogenetic diversity: weighted/unweighted UniFrac distances, Faith's PD, NMDS and PERMANOVA",
        category="individual_omics",
        input_requirements={"microbiome": "required", "metadata": "optional"},
        parameters={
            "weighted": {"type": "bool", "default": True},
            "group_column": {"type": "string", "default": "Visit"},
            "n_permutations": {"type": "int", "default": 999},
        },
        output_spec={"plot_data": "plotly", "distance_matrix": "dataframe", "faith_pd": "dataframe"},
    ),

    "strain_analyzer": ModuleSpec(
        name="strain_analyzer",
        description="Strain-level profiling for a target species from Strain2bScan output (ANI/coverage filtered)",
        category="individual_omics",
        input_requirements={"microbiome": "required"},
        parameters={
            "species": {"type": "string", "default": None},
            "min_ani": {"type": "float", "default": 95.0},
            "min_coverage": {"type": "float", "default": 0.8},
        },
        output_spec={"strain_profile": "dict", "strain_count": "int"},
        constraints=["Requires Strain2bScan-format strain table; picks the most recorded species when none is named"],
    ),

    "source_tracking": ModuleSpec(
        name="source_tracking",
        description="Source tracking (FEAST-style NNLS/EM) estimating source contributions to sink samples",
        category="individual_omics",
        input_requirements={"microbiome": "required", "metadata": "optional"},
        parameters={
            "source_column": {"type": "string", "default": "source_type"},
            "method": {"type": "enum", "options": ["nnls", "em"], "default": "nnls"},
        },
        output_spec={"plot_data": "plotly", "source_proportions": "dataframe"},
    ),

    # ── Preprocessing (R-dependent) ───────────────────────────
    "batch_correction": ModuleSpec(
        name="batch_correction",
        description="ComBat-seq/ComBat/MMUPHin batch effect correction with biological covariate preservation",
        category="preprocessing",
        input_requirements={"data": "required", "metadata": "required"},
        parameters={
            "batch_column": {"type": "string", "required": True},
            "biological_covariates": {"type": "array", "default": []},
            "method": {"type": "enum", "options": ["combat_seq", "combat", "mmuphin"], "default": "combat_seq"},
            "data_type": {"type": "enum", "options": ["microbiome", "metabolome"]},
        },
        output_spec={"corrected_matrix": "dataframe", "combat_params": "dict", "plot_data": "plotly"},
        constraints=["Requires metadata with batch_column"],
        depends_on=["data_validator"],
    ),

    "imputation": ModuleSpec(
        name="imputation",
        description="KNN/random forest/QRILC/half-min/min missing value imputation for MNAR and MAR",
        category="preprocessing",
        input_requirements={"data": "required"},
        parameters={
            "method": {"type": "enum", "options": ["knn", "rf", "qrilc", "half_min", "min"], "default": "knn"},
            "missing_threshold": {"type": "float", "default": 0.5, "range": [0.1, 0.9]},
            "data_type": {"type": "enum", "options": ["microbiome", "metabolome"]},
        },
        output_spec={"imputed_matrix": "dataframe", "imputation_summary": "dict", "plot_data": "plotly"},
        constraints=["Features with missing rate > threshold are removed"],
        depends_on=["data_validator"],
    ),

    # ── Advanced Statistical Tests ──────────────────────────────
    "paired_differential_test": ModuleSpec(
        name="paired_differential_test",
        description="Paired differential abundance test for before-after or matched designs (Wilcoxon signed-rank or ALDEx2)",
        category="marker",
        input_requirements={"microbiome": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "required": True},
            "subject_column": {"type": "string", "required": True},
            "method": {"type": "enum", "options": ["paired_wilcoxon", "paired_aldex2"], "default": "paired_wilcoxon"},
            "transformation": {"type": "enum", "options": ["clr", "ilr", "none"], "default": "clr"},
            "pvalue_threshold": {"type": "float", "default": 0.05},
        },
        output_spec={"significant_features": "dataframe", "volcano_plot": "plotly", "statistics": "dict"},
        constraints=["Requires exactly 2 groups and subject_column for pairing"],
        depends_on=["data_validator"],
    ),

    "ancom_bc": ModuleSpec(
        name="ancom_bc",
        description="ANCOM-BC: bias-corrected differential abundance with covariate adjustment and multi-group support",
        category="marker",
        input_requirements={"microbiome": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "required": True},
            "covariates": {"type": "array", "default": []},
            "random_effects": {"type": "string", "default": None},
            "pvalue_threshold": {"type": "float", "default": 0.05},
        },
        output_spec={"significant_features": "dataframe", "volcano_plot": "plotly", "sensitivity_plot": "plotly"},
        constraints=["Requires raw count matrix (not normalized)"],
        depends_on=["data_validator"],
    ),

    "permanova_strata": ModuleSpec(
        name="permanova_strata",
        description="PERMANOVA with strata for paired or block designs (adonis2), supporting multiple covariates",
        category="individual_omics",
        input_requirements={"data": "required", "metadata": "required"},
        parameters={
            "group_column": {"type": "string", "required": True},
            "strata_column": {"type": "string", "default": None},
            "covariates": {"type": "array", "default": []},
            "distance_metric": {"type": "enum", "options": ["braycurtis", "euclidean", "unweighted_unifrac", "weighted_unifrac", "jaccard"]},
            "n_permutations": {"type": "int", "default": 999},
        },
        output_spec={"statistics": "dict", "significant_variables": "list", "plot_data": "plotly"},
        constraints=["strata_column enables paired/block design correction"],
        depends_on=["data_validator"],
    ),

    # ── Report Generation ───────────────────────────────────────
    "report_generator": ModuleSpec(        name="report_generator",
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
