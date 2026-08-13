"""
Meta2bAnalyst – Agent L3-L5 Intelligent Analysis Engine
=========================================================
L3  MethodRecommender  – rule-based decision tree for analysis method selection
L4  ResultInterpreter   – template-driven natural-language generation
L5  PaperWriter         – structured, publication-ready manuscript drafting

Dependencies: Python stdlib + numpy + pandas (no external LLM APIs).
"""
from __future__ import annotations

import json
import logging
import random
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from app.services.interpretation_engine import EnhancedInterpreter
import pandas as pd

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Shared utilities
# ──────────────────────────────────────────────────────────────────────────────

def _fmt_pvalue(p: Optional[float]) -> str:
    """Return a human-readable p-value string."""
    if p is None:
        return "not reported"
    if p < 0.001:
        return "p < 0.001"
    if p < 0.01:
        return f"p = {p:.4f}"
    return f"p = {p:.3f}"


def _significance_badge(p: Optional[float]) -> str:
    if p is None:
        return "not significant"
    if p < 0.001:
        return "highly significant"
    if p < 0.01:
        return "significant"
    if p < 0.05:
        return "marginally significant"
    return "not significant"


def _cohen_d_effect(d: float) -> str:
    """Return plain-language effect size for Cohen's d."""
    ad = abs(d)
    if ad < 0.2:
        return "negligible"
    if ad < 0.5:
        return "small"
    if ad < 0.8:
        return "moderate"
    return "large"


# ──────────────────────────────────────────────────────────────────────────────
# L3 – MethodRecommender
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MethodRecommendation:
    method: str
    category: str  # e.g. "diversity", "differential", "ordination", "multivariate"
    confidence: float  # 0.0 – 1.0
    justification: str
    prerequisites: List[str] = field(default_factory=list)
    contraindications: List[str] = field(default_factory=list)
    typical_runtime: str = "minutes"
    suggested_parameters: Dict[str, Any] = field(default_factory=dict)


class MethodRecommender:
    """
    Rule-based recommender that scores analysis methods given data
    characteristics and the research question.
    """

    # Mapping: (data_type, study_design, has_metadata, sample_size_category) -> [methods]
    _RULES: List[Tuple[Dict[str, Any], List[MethodRecommendation]]] = []

    def __init__(self):
        self._build_rules()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(
        self,
        data_summary: Dict[str, Any],
        research_question: str,
        top_k: int = 5,
    ) -> List[MethodRecommendation]:
        """
        Return a ranked list of recommended methods.

        Parameters
        ----------
        data_summary : dict
            Expected keys (all optional):
            - data_type       : str  – "amplicon", "metagenomics", "metabolome", "multi-omics"
            - sample_size     : int
            - has_metadata    : bool
            - study_design    : str  – "cross-sectional", "longitudinal", "case-control", "cohort"
            - n_groups        : int  – number of comparison groups
            - feature_count   : int  – OTU / ASV / gene / metabolite count
            - sequencing_platform : str – "illumina", "pacbio", "nanopore", "lc-ms", "gc-ms"
        research_question : str
            Free-text research goal (used for keyword boosting).
        top_k : int
            Number of recommendations to return.
        """
        data_type = (data_summary.get("data_type") or "amplicon").lower()
        sample_size = int(data_summary.get("sample_size", 0))
        has_metadata = bool(data_summary.get("has_metadata", False))
        study_design = (data_summary.get("study_design") or "cross-sectional").lower()
        n_groups = int(data_summary.get("n_groups", 2))
        feature_count = int(data_summary.get("feature_count", 0))
        platform = (data_summary.get("sequencing_platform") or "").lower()

        size_cat = self._size_category(sample_size)
        rq_lower = research_question.lower()

        candidates: List[MethodRecommendation] = []

        for rule, methods in self._RULES:
            if not self._rule_matches(
                rule,
                data_type=data_type,
                study_design=study_design,
                has_metadata=has_metadata,
                size_cat=size_cat,
                n_groups=n_groups,
                feature_count=feature_count,
            ):
                continue
            for m in methods:
                # Deep-copy and adjust confidence via keyword boosting
                boosted = self._boost_confidence(m, rq_lower, data_type, platform)
                candidates.append(boosted)

        # De-duplicate by method name, keep highest confidence
        uniq: Dict[str, MethodRecommendation] = {}
        for c in candidates:
            if c.method not in uniq or c.confidence > uniq[c.method].confidence:
                uniq[c.method] = c

        ranked = sorted(uniq.values(), key=lambda x: x.confidence, reverse=True)
        return ranked[:top_k]

    # ------------------------------------------------------------------
    # Rule matching helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _size_category(n: int) -> str:
        if n < 10:
            return "tiny"
        if n < 30:
            return "small"
        if n < 100:
            return "medium"
        return "large"

    @classmethod
    def _rule_matches(
        cls,
        rule: Dict[str, Any],
        **kwargs,
    ) -> bool:
        for key, allowed in rule.items():
            val = kwargs.get(key)
            if val is None:
                continue
            if isinstance(allowed, (list, tuple, set)):
                if val not in allowed:
                    return False
            elif val != allowed:
                return False
        return True

    @classmethod
    def _boost_confidence(
        cls,
        method: MethodRecommendation,
        rq: str,
        data_type: str,
        platform: str,
    ) -> MethodRecommendation:
        """Copy method and tweak confidence based on keywords / data."""
        score = method.confidence
        # keyword boost
        kw_map = {
            "alpha": ["richness", "diversity", "shannon", "simpson", "evenness", "alpha"],
            "beta": ["composition", "distance", "dissimilarity", "pcoa", "nmds", "pca", "beta"],
            "differential": ["differential", "biomarker", "marker", "diff", "enriched", "depleted", "lda"],
            "network": ["network", "interaction", "correlation", "co-occurrence"],
            "longitudinal": ["time", "longitudinal", "trajectory", "trend", "serial"],
            "functional": ["function", "pathway", "ko", "ec", "go", "metacyc"],
            "strain": ["strain", "subspecies", "ani", "mashtree"],
        }
        for bucket, keywords in kw_map.items():
            if bucket in method.category and any(k in rq for k in keywords):
                score = min(1.0, score + 0.15)
        # platform penalty / boost
        if data_type == "amplicon" and method.method in ("ancom", "aldex2"):
            score = min(1.0, score + 0.1)  # compositional awareness
        if data_type == "metabolome" and method.method in ("maaslin2", "limma"):
            score = min(1.0, score + 0.1)
        # tiny sample penalty for parametric methods
        if method.method in ("deseq2", "edgeR") and "tiny" in rq:
            score = max(0.0, score - 0.2)
        return MethodRecommendation(
            method=method.method,
            category=method.category,
            confidence=round(score, 3),
            justification=method.justification,
            prerequisites=method.prerequisites[:],
            contraindications=method.contraindications[:],
            typical_runtime=method.typical_runtime,
            suggested_parameters=method.suggested_parameters.copy(),
        )

    # ------------------------------------------------------------------
    # Rule database
    # ------------------------------------------------------------------

    def _build_rules(self):
        r = self._RULES

        # ── Amplicon, cross-sectional, 2 groups, small/medium ──────────
        r.append((
            {"data_type": "amplicon", "study_design": "cross-sectional", "has_metadata": True, "size_cat": ["small", "medium", "large"], "n_groups": 2},
            [
                MethodRecommendation(
                    method="alpha_diversity",
                    category="diversity",
                    confidence=0.92,
                    justification="Standard first-step characterization of within-sample diversity for amplicon data with two groups.",
                    prerequisites=["rarefied_feature_table", "sample_metadata"],
                    suggested_parameters={"metrics": ["shannon", "simpson", "observed_otus"], "group_column": "group"},
                ),
                MethodRecommendation(
                    method="permanova",
                    category="multivariate",
                    confidence=0.90,
                    justification="PERMANOVA on Bray-Curtis or weighted UniFrac distance tests compositional differences between groups.",
                    prerequisites=["distance_matrix", "sample_metadata"],
                    suggested_parameters={"distance": "braycurtis", "n_permutations": 999},
                ),
                MethodRecommendation(
                    method="lefse",
                    category="differential",
                    confidence=0.85,
                    justification="LEfSe identifies biomarkers with LDA score > 2; well-suited for two-group 16S studies.",
                    prerequisites=["relative_abundance_table", "sample_metadata"],
                    suggested_parameters={"lda_threshold": 2.0, "strict": 0.05, "multiclass_strat": False},
                ),
                MethodRecommendation(
                    method="ancom",
                    category="differential",
                    confidence=0.80,
                    justification="ANCOM is a conservative compositional test; good when you need robust differential abundance calls.",
                    prerequisites=["feature_table", "sample_metadata"],
                    suggested_parameters={"cutoff": 0.6},
                ),
                MethodRecommendation(
                    method="pcoa",
                    category="ordination",
                    confidence=0.88,
                    justification="PCoA provides intuitive 2-D/3-D visualisation of beta-diversity patterns.",
                    prerequisites=["distance_matrix"],
                    suggested_parameters={"distance": "braycurtis", "n_components": 3},
                ),
            ]
        ))

        # ── Amplicon, cross-sectional, >2 groups ───────────────────────
        r.append((
            {"data_type": "amplicon", "study_design": "cross-sectional", "has_metadata": True, "size_cat": ["small", "medium", "large"], "n_groups": [3, 4, 5, 6, 7, 8, 9, 10]},
            [
                MethodRecommendation(
                    method="permanova",
                    category="multivariate",
                    confidence=0.92,
                    justification="With multiple groups, PERMANOVA tests overall community differences; follow with pairwise tests if significant.",
                    suggested_parameters={"distance": "braycurtis", "n_permutations": 999, "pairwise": True},
                ),
                MethodRecommendation(
                    method="kruskal_wallis_alpha",
                    category="diversity",
                    confidence=0.88,
                    justification="Kruskal-Wallis extends alpha-diversity comparison to >2 groups (non-parametric, no normality assumption).",
                    prerequisites=["alpha_diversity_vector", "sample_metadata"],
                ),
                MethodRecommendation(
                    method="lefse",
                    category="differential",
                    confidence=0.86,
                    justification="LEfSe multiclass mode handles multiple groups; LDA scores rank discriminative features.",
                    suggested_parameters={"lda_threshold": 2.0, "multiclass_strat": True},
                ),
                MethodRecommendation(
                    method="maaslin2",
                    category="differential",
                    confidence=0.82,
                    justification="MaAsLin2 fits multivariable linear models; useful when adjusting for covariates across multiple groups.",
                    prerequisites=["feature_table", "sample_metadata"],
                    suggested_parameters={"normalization": "TSS", "transform": "LOG", "analysis_method": "LM"},
                ),
            ]
        ))

        # ── Amplicon, longitudinal ─────────────────────────────────────
        r.append((
            {"data_type": "amplicon", "study_design": "longitudinal", "has_metadata": True, "size_cat": ["small", "medium", "large"]},
            [
                MethodRecommendation(
                    method="mixed_effects_alpha",
                    category="diversity",
                    confidence=0.90,
                    justification="Linear mixed-effects models account for repeated measures per subject over time.",
                    prerequisites=["alpha_diversity_vector", "sample_metadata_with_timepoint"],
                    suggested_parameters={"fixed_effects": ["timepoint", "group"], "random_effects": "subject_id"},
                ),
                MethodRecommendation(
                    method="permanova_blocked",
                    category="multivariate",
                    confidence=0.88,
                    justification="Blocked PERMANOVA (Adonis2 with strata) controls for inter-subject variation in longitudinal designs.",
                    prerequisites=["distance_matrix", "sample_metadata"],
                    suggested_parameters={"strata": "subject_id", "distance": "braycurtis"},
                ),
                MethodRecommendation(
                    method="maaslin2_longitudinal",
                    category="differential",
                    confidence=0.86,
                    justification="MaAsLin2 supports random-intercept models for longitudinal differential abundance.",
                    suggested_parameters={"fixed_effects": ["timepoint", "group"], "random_effects": ["subject_id"]},
                ),
                MethodRecommendation(
                    method="songbird",
                    category="differential",
                    confidence=0.78,
                    justification="Songbird (multinomial regression) models differential rank and can include time as a continuous covariate.",
                    prerequisites=["feature_table", "sample_metadata"],
                    suggested_parameters={"epochs": 10000, "differential_prior": 0.5},
                ),
            ]
        ))

        # ── Metagenomics (shotgun) ─────────────────────────────────────
        r.append((
            {"data_type": "metagenomics", "has_metadata": True, "size_cat": ["small", "medium", "large"]},
            [
                MethodRecommendation(
                    method="humann3_functional",
                    category="functional",
                    confidence=0.90,
                    justification="HUMAnN3 gene-family and pathway profiles are the standard functional read-out for shotgun metagenomes.",
                    prerequisites=["metagenomic_reads", "metaphlan_profiles"],
                    suggested_parameters={"nucleotide_db": "chocophlan", "protein_db": "uniref"},
                ),
                MethodRecommendation(
                    method="metaphlan_taxonomy",
                    category="taxonomy",
                    confidence=0.92,
                    justification="MetaPhlAn taxonomic profiles provide species-level resolution with minimal computational cost.",
                    suggested_parameters={"min_abundance": 0.01, "ignore_eukaryotes": True},
                ),
                MethodRecommendation(
                    method="deseq2_metagenomics",
                    category="differential",
                    confidence=0.85,
                    justification="DESeq2 on gene-family counts (rounded) works well for medium-to-large shotgun cohorts.",
                    prerequisites=["gene_family_count_table", "sample_metadata"],
                    suggested_parameters={"fitType": "parametric", "betaPrior": True},
                ),
            ]
        ))

        # ── Metabolomics ───────────────────────────────────────────────
        r.append((
            {"data_type": "metabolome", "has_metadata": True, "size_cat": ["small", "medium", "large"]},
            [
                MethodRecommendation(
                    method="pca_metabolome",
                    category="ordination",
                    confidence=0.90,
                    justification="PCA on log-transformed metabolite intensities reveals major variance structure and batch effects.",
                    prerequisites=["metabolite_intensity_matrix"],
                    suggested_parameters={"scaling": "pareto", "log_transform": True},
                ),
                MethodRecommendation(
                    method="pls_da",
                    category="multivariate",
                    confidence=0.85,
                    justification="PLS-DA maximises group separation and provides VIP scores for metabolite importance ranking.",
                    prerequisites=["metabolite_intensity_matrix", "sample_metadata"],
                    suggested_parameters={"n_components": 2, "validation": "CV", "nperm": 200},
                ),
                MethodRecommendation(
                    method="limma_metabolome",
                    category="differential",
                    confidence=0.82,
                    justification="limma (moderated t-statistic) offers excellent power for metabolomics with small sample sizes.",
                    prerequisites=["metabolite_intensity_matrix", "sample_metadata"],
                    suggested_parameters={"normalize.method": "quantile", "trend": True},
                ),
                MethodRecommendation(
                    method="volcano_plot",
                    category="visualisation",
                    confidence=0.80,
                    justification="Volcano plots summarise fold-change vs. statistical significance for all metabolites.",
                    prerequisites=["differential_results_table"],
                ),
            ]
        ))

        # ── Multi-omics (any data_type hint) ───────────────────────────
        r.append((
            {"data_type": "multi-omics", "has_metadata": True, "size_cat": ["medium", "large"]},
            [
                MethodRecommendation(
                    method="procrustes",
                    category="integration",
                    confidence=0.88,
                    justification="Procrustes analysis tests concordance between microbiome and metabolome ordinations.",
                    prerequisites=["distance_matrix_microbiome", "distance_matrix_metabolome"],
                    suggested_parameters={"symmetric": True, "permutations": 999},
                ),
                MethodRecommendation(
                    method="moofa",
                    category="integration",
                    confidence=0.86,
                    justification="MOFA+ decomposes multi-omic variance into shared latent factors across modalities.",
                    prerequisites=["feature_table_microbiome", "feature_table_metabolome", "sample_metadata"],
                    suggested_parameters={"n_factors": 10, "spikeslab_factors": True},
                ),
                MethodRecommendation(
                    method="diablo",
                    category="integration",
                    confidence=0.84,
                    justification="DIABLO (mixOmics) builds a supervised multi-omic classifier and extracts discriminative features.",
                    prerequisites=["feature_table_microbiome", "feature_table_metabolome", "sample_metadata"],
                    suggested_parameters={"design": "full", "ncomp": 2},
                ),
                MethodRecommendation(
                    method="sparse_cca",
                    category="integration",
                    confidence=0.78,
                    justification="Sparse CCA identifies maximally correlated sparse feature sets between two omics layers.",
                    prerequisites=["feature_table_x", "feature_table_y"],
                    suggested_parameters={"n_components": 2, "penaltyx": 0.3, "penaltyz": 0.3},
                ),
            ]
        ))

        # ── No metadata fallback ───────────────────────────────────────
        r.append((
            {"has_metadata": False, "size_cat": ["small", "medium", "large"]},
            [
                MethodRecommendation(
                    method="rarefaction",
                    category="preprocessing",
                    confidence=0.95,
                    justification="Without metadata the analysis is descriptive; rarefaction normalises sampling depth first.",
                    prerequisites=["feature_table"],
                ),
                MethodRecommendation(
                    method="taxonomy_bar",
                    category="visualisation",
                    confidence=0.90,
                    justification="Taxonomy bar plots summarise community composition without requiring metadata.",
                    prerequisites=["feature_table_with_taxonomy"],
                ),
                MethodRecommendation(
                    method="core_microbiome",
                    category="characterisation",
                    confidence=0.82,
                    justification="Core microbiome analysis identifies taxa present in most samples (prevalence-based, no metadata needed).",
                    prerequisites=["feature_table"],
                    suggested_parameters={"prevalence_cutoff": 0.5, "abundance_cutoff": 0.01},
                ),
            ]
        ))

        # ── Tiny sample fallback ───────────────────────────────────────
        r.append((
            {"size_cat": "tiny"},
            [
                MethodRecommendation(
                    method="descriptive_summary",
                    category="exploratory",
                    confidence=0.95,
                    justification="With <10 samples, inferential statistics are unreliable; focus on descriptive summaries and visualisation.",
                    prerequisites=["feature_table"],
                ),
                MethodRecommendation(
                    method="taxonomy_bar",
                    category="visualisation",
                    confidence=0.85,
                    justification="Bar plots and heatmaps provide useful qualitative overviews even with very small cohorts.",
                    prerequisites=["feature_table_with_taxonomy"],
                ),
                MethodRecommendation(
                    method="aldex2",
                    category="differential",
                    confidence=0.65,
                    justification="ALDEx2 is conservative and can be run on small samples, but expect low power and wide CIs.",
                    prerequisites=["feature_table", "sample_metadata"],
                    contraindications=["n_per_group < 3"],
                    suggested_parameters={"test": "welch", "effect": True},
                ),
            ]
        ))


# ──────────────────────────────────────────────────────────────────────────────
# L4 – ResultInterpreter
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class InterpretationResult:
    summary: str
    detailed: str
    clinical_relevance: Optional[str] = None
    caveats: List[str] = field(default_factory=list)
    follow_up_suggestions: List[str] = field(default_factory=list)


class ResultInterpreter:
    """
    Template-based natural-language generator for microbiome / multi-omics
    analysis results.  No LLM – deterministic rule + template filling.
    """

    def __init__(self):
        self._templates = self._load_templates()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def interpret(
        self,
        analysis_type: str,
        statistics: Dict[str, Any],
        plot_data: Optional[Dict[str, Any]] = None,
    ) -> InterpretationResult:
        """
        Generate a natural-language interpretation of analysis results.

        Parameters
        ----------
        analysis_type : str
            One of: alpha, beta, differential, ordination, correlation,
            lefse, ancom, deseq2, aldex2, maaslin2, functional, network,
            taxonomy, metabolome_pca, metabolome_plsda.
        statistics : dict
            Analysis-specific summary statistics.
        plot_data : dict, optional
            Visualisation metadata (axis labels, group colours, etc.).
        """
        atype = analysis_type.lower().replace("-", "_")
        handler = getattr(self, f"_interp_{atype}", self._interp_generic)
        return handler(statistics, plot_data or {})

    # ------------------------------------------------------------------
    # Template helpers
    # ------------------------------------------------------------------

    def _load_templates(self) -> Dict[str, Any]:
        """Return the in-memory template dictionary (no external files)."""
        return {
            "alpha": {
                "sig_up": "Alpha diversity analysis revealed significantly {higher_lower} {metric} diversity in the {group_name} group ({pvalue}), suggesting {direction} community richness compared to {reference_group}.",
                "sig_up_effect": "The effect size was {effect_size} (Cohen's d = {cohen_d}), indicating a {effect_label} biological difference.",
                "not_sig": "No significant difference in {metric} diversity was observed between groups ({pvalue}), indicating that {group_name} and {reference_group} harbour comparable within-sample community diversity.",
            },
            "beta": {
                "sig": "Beta-diversity analysis ({distance} distance) demonstrated a significant separation between groups ({pvalue}; R² = {r2}), indicating that the {group_name} condition is associated with a distinct community composition.",
                "not_sig": "No significant community compositional differences were detected between groups ({pvalue}; R² = {r2}), suggesting that the microbiome structure is largely similar across {group_name} and {reference_group}.",
            },
            "differential": {
                "sig": "Differential abundance testing identified {n_sig} significantly {enriched_depleted} feature(s) in {group_name} (FDR < {fdr_threshold}). The top hit, {top_feature} (log2FC = {log2fc}, adj. p = {adj_p}), suggests a biologically relevant shift in this taxon / function.",
                "not_sig": "No features survived multiple-testing correction (FDR < {fdr_threshold}) in the differential abundance analysis, suggesting that the overall taxonomic / functional profile is not substantially altered in {group_name}.",
            },
            "ordination": {
                "pcoa": "Principal Coordinate Analysis (PCoA) based on {distance} distances revealed {separation} along PC{pc_axis} ({var_explained:.1f}% variance explained).",
            },
            "correlation": {
                "sig": "Correlation analysis detected {n_sig} significant associations (|{method}| ≥ {threshold}, FDR < {fdr}). The strongest association involved {top_feature} and {top_correlate} ({method} = {top_r}, {pvalue}).",
            },
            "functional": {
                "sig": "Functional profiling indicated {n_enriched} enriched and {n_depleted} depleted pathways in {group_name} (FDR < {fdr}). Notably, {top_pathway} was significantly altered (log2FC = {log2fc}), implicating {pathway_role} in the host phenotype.",
            },
            "network": {
                "summary": "Co-occurrence network inference ({method}) produced a graph with {n_nodes} nodes and {n_edges} edges (density = {density}). The network exhibited {modularity} modularity (Q = {modularity_score}), suggesting {community_structure} community structure among the microbial taxa.",
            },
            "metabolome_pca": {
                "sig": "PCA of metabolite profiles showed clear {group_name}-driven separation along PC{pc_axis} ({var_explained:.1f}% variance explained), indicating that the metabolic phenotype is strongly associated with the experimental condition.",
                "not_sig": "PCA revealed no pronounced group-driven clustering; the first two components captured {cum_var:.1f}% of total variance, with substantial overlap between {group_name} and {reference_group}.",
            },
            "metabolome_plsda": {
                "sig": "PLS-DA achieved robust group discrimination (R²Y = {r2y}, Q² = {q2}), with VIP scores highlighting {top_metabolite} as the most discriminatory metabolite (VIP = {top_vip}).",
            },
        }

    @staticmethod
    def _fill(template: str, mapping: Dict[str, Any]) -> str:
        """Simple template filling with safe defaults."""
        result = template
        for key, val in mapping.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                if isinstance(val, float):
                    result = result.replace(placeholder, f"{val:.3f}")
                else:
                    result = result.replace(placeholder, str(val))
        # Clean un-filled placeholders
        result = re.sub(r"\{[a-zA-Z0-9_]+\}", "—", result)
        return result

    # ------------------------------------------------------------------
    # Specific interpreters
    # ------------------------------------------------------------------

    def _interp_alpha(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        metric = stats.get("metric", "Shannon")
        pvalue = stats.get("pvalue")
        group_name = stats.get("group_name", "treatment")
        reference_group = stats.get("reference_group", "control")
        higher_lower = stats.get("direction", "higher")
        cohen_d = stats.get("cohen_d")
        mean_diff = stats.get("mean_difference")

        tpl = self._templates["alpha"]
        lines: List[str] = []

        if pvalue is not None and pvalue < 0.05:
            lines.append(self._fill(tpl["sig_up"], {
                "metric": metric, "higher_lower": higher_lower,
                "group_name": group_name, "pvalue": _fmt_pvalue(pvalue),
                "direction": "reduced" if higher_lower == "lower" else "increased",
                "reference_group": reference_group,
            }))
            if cohen_d is not None:
                lines.append(self._fill(tpl["sig_up_effect"], {
                    "effect_size": _cohen_d_effect(cohen_d),
                    "cohen_d": cohen_d,
                    "effect_label": _cohen_d_effect(cohen_d),
                }))
        else:
            lines.append(self._fill(tpl["not_sig"], {
                "metric": metric, "pvalue": _fmt_pvalue(pvalue),
                "group_name": group_name, "reference_group": reference_group,
            }))

        caveats = []
        if pvalue is not None and 0.05 <= pvalue < 0.1:
            caveats.append("The p-value is borderline; a larger sample may clarify significance.")
        if stats.get("sample_size", 0) < 20:
            caveats.append("Small sample size limits statistical power for alpha-diversity comparisons.")

        follow_up = []
        if pvalue is not None and pvalue < 0.05:
            follow_up.append(f"Consider beta-diversity and differential abundance analyses to complement {metric} findings.")
            follow_up.append("Evaluate whether the diversity shift is driven by specific taxa or a broad community change.")
        else:
            follow_up.append("Even without alpha-diversity differences, compositional or functional shifts may exist.")

        return InterpretationResult(
            summary=lines[0],
            detailed=" ".join(lines),
            clinical_relevance=None,
            caveats=caveats,
            follow_up_suggestions=follow_up,
        )

    def _interp_beta(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        pvalue = stats.get("pvalue")
        r2 = stats.get("r2")
        distance = stats.get("distance_metric", "Bray-Curtis")
        group_name = stats.get("group_name", "treatment")
        reference_group = stats.get("reference_group", "control")

        tpl = self._templates["beta"]
        if pvalue is not None and pvalue < 0.05:
            summary = self._fill(tpl["sig"], {
                "distance": distance, "pvalue": _fmt_pvalue(pvalue),
                "r2": r2, "group_name": group_name,
            })
            clinical = f"The significant compositional shift in {group_name} may reflect dysbiosis or a treatment-induced community restructuring."
        else:
            summary = self._fill(tpl["not_sig"], {
                "pvalue": _fmt_pvalue(pvalue), "r2": r2,
                "group_name": group_name, "reference_group": reference_group,
            })
            clinical = f"Microbiome composition appears stable across {group_name} and {reference_group}, which may indicate resilience to the experimental intervention."

        caveats = []
        if r2 is not None and r2 < 0.05:
            caveats.append(f"Although statistically significant, the effect size is small (R² = {r2:.3f}); biological relevance should be assessed cautiously.")

        follow_up = [
            "Follow with differential abundance testing to identify specific taxa driving the community shift.",
            "Consider PERMDISP to verify that variance homogeneity assumptions hold.",
        ] if (pvalue is not None and pvalue < 0.05) else [
            "Explore taxonomic bar plots and core-microbiome analysis for qualitative patterns.",
        ]

        return InterpretationResult(
            summary=summary,
            detailed=summary,
            clinical_relevance=clinical,
            caveats=caveats,
            follow_up_suggestions=follow_up,
        )

    def _interp_differential(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        n_sig = stats.get("n_significant", 0)
        fdr = stats.get("fdr_threshold", 0.05)
        group_name = stats.get("group_name", "treatment")
        top_feature = stats.get("top_feature", "—")
        log2fc = stats.get("top_log2fc")
        adj_p = stats.get("top_adj_p")
        enriched_depleted = stats.get("direction", "altered")

        tpl = self._templates["differential"]
        if n_sig > 0:
            summary = self._fill(tpl["sig"], {
                "n_sig": n_sig, "enriched_depleted": enriched_depleted,
                "group_name": group_name, "fdr_threshold": fdr,
                "top_feature": top_feature, "log2fc": log2fc,
                "adj_p": _fmt_pvalue(adj_p),
            })
        else:
            summary = self._fill(tpl["not_sig"], {
                "fdr_threshold": fdr, "group_name": group_name,
            })

        caveats = []
        if stats.get("sparsity", 0) > 0.8:
            caveats.append("High data sparsity may reduce sensitivity; consider rarefaction or imputation.")
        if stats.get("method") in ("deseq2", "edgeR") and stats.get("sample_size", 0) < 20:
            caveats.append("Parametric methods with small samples can yield anti-conservative p-values; verify with ALDEx2 or ANCOM.")

        follow_up = [
            "Validate top hits with qPCR or targeted sequencing if feasible.",
            "Investigate whether significant taxa belong to known functional guilds (e.g., butyrate producers).",
        ] if n_sig > 0 else [
            "Increase sample size or reduce feature granularity (e.g., genus-level aggregation) to improve power.",
            "Consider functional profiling if taxonomic differences are absent but a phenotype is present.",
        ]

        return InterpretationResult(
            summary=summary,
            detailed=summary,
            caveats=caveats,
            follow_up_suggestions=follow_up,
        )

    def _interp_lefse(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        # LEfSe is a special case of differential
        return self._interp_differential(stats, plot_data)

    def _interp_ancom(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        return self._interp_differential(stats, plot_data)

    def _interp_deseq2(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        return self._interp_differential(stats, plot_data)

    def _interp_aldex2(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        return self._interp_differential(stats, plot_data)

    def _interp_maaslin2(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        return self._interp_differential(stats, plot_data)

    def _interp_ordination(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        distance = stats.get("distance_metric", "Bray-Curtis")
        pc_axis = stats.get("pc_axis", 1)
        var_explained = stats.get("variance_explained", 0.0)
        separation = stats.get("separation_quality", "partial")

        tpl = self._templates["ordination"]
        summary = self._fill(tpl["pcoa"], {
            "distance": distance, "separation": separation,
            "pc_axis": pc_axis, "var_explained": var_explained,
        })

        return InterpretationResult(
            summary=summary,
            detailed=summary,
            follow_up_suggestions=[
                "Examine loadings to identify features contributing most to the major axes.",
                "Overlay metadata gradients (e.g., pH, age) as vectors if available.",
            ],
        )

    def _interp_pcoa(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        return self._interp_ordination(stats, plot_data)

    def _interp_nmds(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        return self._interp_ordination(stats, plot_data)

    def _interp_correlation(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        n_sig = stats.get("n_significant", 0)
        method = stats.get("correlation_method", "Spearman")
        threshold = stats.get("threshold", 0.3)
        fdr = stats.get("fdr_threshold", 0.05)
        top_feature = stats.get("top_feature", "—")
        top_correlate = stats.get("top_correlate", "—")
        top_r = stats.get("top_r")
        top_p = stats.get("top_p")

        tpl = self._templates["correlation"]
        summary = self._fill(tpl["sig"], {
            "n_sig": n_sig, "method": method,
            "threshold": threshold, "fdr": fdr,
            "top_feature": top_feature, "top_correlate": top_correlate,
            "top_r": top_r, "pvalue": _fmt_pvalue(top_p),
        })

        caveats = []
        if method.lower() == "pearson" and stats.get("data_nonnormal", False):
            caveats.append("Pearson correlation assumes bivariate normality; Spearman may be more appropriate.")

        return InterpretationResult(
            summary=summary,
            detailed=summary,
            caveats=caveats,
            follow_up_suggestions=[
                "Construct network graphs from significant correlations to reveal hub taxa.",
                "Assess whether correlations are driven by confounding variables (e.g., diet, medication).",
            ] if n_sig > 0 else [
                "Increase sample size or stratify by known confounders.",
            ],
        )

    def _interp_functional(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        n_enriched = stats.get("n_enriched", 0)
        n_depleted = stats.get("n_depleted", 0)
        fdr = stats.get("fdr_threshold", 0.05)
        group_name = stats.get("group_name", "treatment")
        top_pathway = stats.get("top_pathway", "—")
        log2fc = stats.get("top_log2fc")
        pathway_role = stats.get("pathway_role", "metabolic processes")

        tpl = self._templates["functional"]
        summary = self._fill(tpl["sig"], {
            "n_enriched": n_enriched, "n_depleted": n_depleted,
            "group_name": group_name, "fdr": fdr,
            "top_pathway": top_pathway, "log2fc": log2fc,
            "pathway_role": pathway_role,
        })

        return InterpretationResult(
            summary=summary,
            detailed=summary,
            follow_up_suggestions=[
                "Map significant pathways to KEGG or MetaCyc for mechanistic interpretation.",
                "Integrate with metabolomics data to confirm functional predictions.",
            ] if (n_enriched + n_depleted) > 0 else [
                "Check input gene-family abundance thresholds; low coverage can suppress pathway signals.",
            ],
        )

    def _interp_network(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        n_nodes = stats.get("n_nodes", 0)
        n_edges = stats.get("n_edges", 0)
        density = stats.get("density", 0.0)
        modularity = stats.get("modularity_score", 0.0)
        method = stats.get("network_method", "SparCC")

        tpl = self._templates["network"]
        community_structure = "strong" if modularity > 0.4 else "weak"
        summary = self._fill(tpl["summary"], {
            "method": method, "n_nodes": n_nodes, "n_edges": n_edges,
            "density": density, "modularity": "high" if modularity > 0.4 else "low",
            "modularity_score": modularity, "community_structure": community_structure,
        })

        return InterpretationResult(
            summary=summary,
            detailed=summary,
            follow_up_suggestions=[
                "Identify hub nodes (high degree / betweenness) as potential keystone taxa.",
                "Compare network topology between conditions using differential network analysis.",
            ],
        )

    def _interp_metabolome_pca(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        pvalue = stats.get("pvalue")
        pc_axis = stats.get("pc_axis", 1)
        var_explained = stats.get("variance_explained", 0.0)
        group_name = stats.get("group_name", "treatment")
        reference_group = stats.get("reference_group", "control")
        cum_var = stats.get("cumulative_variance", 0.0)

        tpl = self._templates["metabolome_pca"]
        if pvalue is not None and pvalue < 0.05:
            summary = self._fill(tpl["sig"], {
                "group_name": group_name, "pc_axis": pc_axis,
                "var_explained": var_explained,
            })
        else:
            summary = self._fill(tpl["not_sig"], {
                "cum_var": cum_var, "group_name": group_name,
                "reference_group": reference_group,
            })

        return InterpretationResult(
            summary=summary,
            detailed=summary,
            follow_up_suggestions=[
                "Investigate loadings to pinpoint metabolites driving the separation.",
                "Apply PLS-DA for supervised discrimination and VIP ranking.",
            ] if (pvalue is not None and pvalue < 0.05) else [
                "Consider orthogonal filters to remove batch effects before re-analysis.",
                "Apply PLS-DA or OPLS-DA to maximise group separation.",
            ],
        )

    def _interp_metabolome_plsda(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        r2y = stats.get("r2y")
        q2 = stats.get("q2")
        top_metabolite = stats.get("top_metabolite", "—")
        top_vip = stats.get("top_vip")

        tpl = self._templates["metabolome_plsda"]
        summary = self._fill(tpl["sig"], {
            "r2y": r2y, "q2": q2,
            "top_metabolite": top_metabolite, "top_vip": top_vip,
        })

        caveats = []
        if q2 is not None and q2 < 0.5:
            caveats.append("Q² < 0.5 indicates limited predictive power; cross-validate with independent data.")

        return InterpretationResult(
            summary=summary,
            detailed=summary,
            caveats=caveats,
            follow_up_suggestions=[
                "Validate VIP-ranked metabolites with targeted MS/MS or NMR.",
                "Map top metabolites to KEGG pathways for mechanistic context.",
            ],
        )

    def _interp_generic(self, stats: Dict[str, Any], plot_data: Dict[str, Any]) -> InterpretationResult:
        summary = stats.get("summary", "Analysis completed; no specific interpretation template is available for this analysis type.")
        return InterpretationResult(
            summary=summary,
            detailed=summary,
            follow_up_suggestions=["Consult the method documentation for domain-specific interpretation guidance."],
        )


# ──────────────────────────────────────────────────────────────────────────────
# L5 – PaperWriter
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PaperSection:
    section_type: str
    title: str
    content: str
    word_count: int
    keywords: List[str] = field(default_factory=list)


class PaperWriter:
    """
    Rule-based manuscript section generator for microbiome / multi-omics
    studies.  Uses structured templates and analysis history to build a
    coherent narrative.  No LLM calls.
    """

    # Standard citations referenced automatically
    _CITATIONS = {
        "qiime2": "Bolyen et al., 2019, Nature Biotechnology (QIIME 2)",
        "phyloseq": "McMurdie & Holmes, 2013, PLoS ONE (phyloseq)",
        "dada2": "Callahan et al., 2016, Nature Methods (DADA2)",
        "deseq2": "Love et al., 2014, Genome Biology (DESeq2)",
        "lefse": "Segata et al., 2011, Genome Biology (LEfSe)",
        "ancom": "Mandal et al., 2015, Microbiome (ANCOM)",
        "aldex2": "Fernandes et al., 2014, PLoS ONE (ALDEx2)",
        "maaslin2": "Mallick et al., 2021, PLoS Computational Biology (MaAsLin2)",
        "permanova": "Anderson, 2001, Austral Ecology (PERMANOVA)",
        "humann3": "Beghini et al., 2021, Nature Methods (HUMAnN 3)",
        "metaphlan": "Beghini et al., 2021, Nature Methods (MetaPhlAn 4)",
        "r": "R Core Team, 2024, R: A Language and Environment for Statistical Computing",
        "vegan": "Oksanen et al., 2022, vegan: Community Ecology Package",
    }

    def __init__(self):
        self._history: List[Dict[str, Any]] = []

    def add_analysis_record(self, record: Dict[str, Any]):
        """Append an analysis result to the internal history log."""
        self._history.append(record)

    def write_section(
        self,
        section_type: str,
        results_summary: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> PaperSection:
        """
        Generate a single manuscript section.

        Parameters
        ----------
        section_type : str
            One of: abstract, introduction, methods, results, discussion,
            conclusions, keywords.
        results_summary : dict
            High-level study descriptors (title, design, n_samples, data_type,
            key_findings, etc.).
        context : dict, optional
            Additional narrative context (study_name, journal_target, etc.).
        """
        ctx = context or {}
        handler = getattr(self, f"_write_{section_type.lower()}", self._write_generic)
        return handler(results_summary, ctx)

    def write_full_paper(
        self,
        results_summary: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, PaperSection]:
        """Generate all standard sections at once."""
        sections = {}
        for st in ("abstract", "introduction", "methods", "results", "discussion", "conclusions"):
            sections[st] = self.write_section(st, results_summary, context)
        return sections

    # ------------------------------------------------------------------
    # Section generators
    # ------------------------------------------------------------------

    def _write_abstract(self, rs: Dict[str, Any], ctx: Dict[str, Any]) -> PaperSection:
        title = rs.get("title", ctx.get("study_name", "Untitled Microbiome Study"))
        background = rs.get("background", "The human microbiome plays a critical role in health and disease. However, the microbial signatures associated with specific conditions remain incompletely characterised.")
        objective = rs.get("objective", "To characterise the microbiome composition and identify differentially abundant taxa between study groups.")
        methods = rs.get("methods_summary", self._methods_summary_from_history())
        n_samples = rs.get("n_samples", "N")
        data_type = rs.get("data_type", "16S rRNA amplicon")
        key_findings = rs.get("key_findings", ["No key findings were pre-specified."])
        conclusion = rs.get("conclusion", "These findings contribute to our understanding of microbiome dynamics and may inform future mechanistic studies.")

        content = textwrap.dedent(f"""\
            Background: {background}
            Objective: {objective}
            Methods: {methods} A total of {n_samples} samples were profiled using {data_type} sequencing. Quality control, taxonomic assignment, and statistical analyses were performed using established bioinformatics pipelines.
            Results: {" ".join(key_findings)}
            Conclusions: {conclusion}
        """)
        return PaperSection(
            section_type="abstract",
            title="Abstract",
            content=content.strip(),
            word_count=len(content.split()),
            keywords=rs.get("keywords", ["microbiome", "16S rRNA", "differential abundance", "bioinformatics"]),
        )

    def _write_introduction(self, rs: Dict[str, Any], ctx: Dict[str, Any]) -> PaperSection:
        background = rs.get("background", "The gut microbiome has emerged as a key regulator of host physiology, influencing metabolism, immunity, and even neurological function.")
        gap = rs.get("knowledge_gap", "Despite growing interest, the specific microbial taxa and functional pathways driving disease phenotypes remain poorly defined.")
        objective = rs.get("objective", "Here, we aimed to systematically characterise the microbiome landscape and identify robust biomarkers associated with the condition of interest.")
        hypothesis = rs.get("hypothesis", "We hypothesised that the study groups would exhibit distinct microbiome profiles characterised by differential abundance of specific taxa.")

        content = textwrap.dedent(f"""\
            {background} Advances in high-throughput sequencing have enabled culture-independent surveys of complex microbial communities, revealing associations between microbiome composition and a wide range of health outcomes.

            {gap} Existing studies have been limited by small sample sizes, heterogeneous methodologies, and lack of functional validation. Consequently, there is a pressing need for well-powered, standardised analyses that integrate taxonomic and functional profiling.

            {objective} To address this gap, we conducted a comprehensive {rs.get('study_design', 'cross-sectional')} analysis of {rs.get('n_samples', 'N')} {rs.get('sample_type', 'faecal')} samples. {hypothesis} By applying rigorous statistical frameworks and controlling for confounding variables, we sought to identify reproducible microbial signatures with potential translational relevance.
        """)
        return PaperSection(
            section_type="introduction",
            title="Introduction",
            content=content.strip(),
            word_count=len(content.split()),
        )

    def _write_methods(self, rs: Dict[str, Any], ctx: Dict[str, Any]) -> PaperSection:
        data_type = rs.get("data_type", "16S rRNA amplicon")
        n_samples = rs.get("n_samples", "N")
        platform = rs.get("sequencing_platform", "Illumina MiSeq")
        region = rs.get("target_region", "V3-V4")
        qc = rs.get("qc_steps", "Samples with fewer than 10,000 reads were excluded. Adapters and low-quality bases were trimmed using Cutadapt.")
        tax_assignment = rs.get("tax_assignment", "Taxonomic assignment was performed using the DADA2 pipeline against the SILVA 138 reference database.")
        norm = rs.get("normalisation", "Feature tables were rarefied to the minimum sampling depth for alpha-diversity analyses. Relative abundance (TSS) normalisation was used for compositional methods.")
        stats = rs.get("statistical_methods", self._stats_methods_from_history())
        sw = rs.get("software", "QIIME 2 (v2024.2) and R (v4.3) with the phyloseq and vegan packages.")
        ethics = rs.get("ethics", "This study was approved by the institutional ethics committee.")

        content = textwrap.dedent(f"""\
            Study design and sample collection
            {rs.get('study_design', 'Cross-sectional')} {rs.get('sample_type', 'faecal')} samples were collected from {n_samples} participants. {rs.get('collection_protocol', 'Samples were immediately frozen at −80 °C until DNA extraction.')}

            {data_type.capitalize()} sequencing
            DNA was extracted using a commercial kit according to the manufacturer's instructions. The {region} hypervariable region of the bacterial 16S rRNA gene was amplified and sequenced on the {platform} platform using paired-end {rs.get('read_length', '2 × 250 bp')} chemistry.

            Bioinformatics processing
            {qc} {tax_assignment} A phylogenetic tree was constructed with MAFFT and FastTree for UniFrac distance calculations.

            Normalisation and quality control
            {norm}

            Statistical analysis
            {stats}

            Software and reproducibility
            All analyses were conducted in {sw} Code and processed data are available upon reasonable request.

            Ethics statement
            {ethics}
        """)
        return PaperSection(
            section_type="methods",
            title="Methods",
            content=content.strip(),
            word_count=len(content.split()),
        )

    def _write_results(self, rs: Dict[str, Any], ctx: Dict[str, Any]) -> PaperSection:
        data_type = rs.get("data_type", "16S rRNA amplicon")
        n_samples = rs.get("n_samples", "N")
        n_features = rs.get("n_features", "M")
        findings = rs.get("key_findings", [])
        alpha_result = rs.get("alpha_result")
        beta_result = rs.get("beta_result")
        diff_result = rs.get("differential_result")

        paragraphs: List[str] = []
        paragraphs.append(
            f"After quality filtering, {n_samples} samples remained for analysis, yielding a total of {n_features} {data_type} features. "
            f"Rarefaction curves indicated adequate sequencing depth for diversity estimation (Figure S1)."
        )

        if alpha_result:
            p = alpha_result.get("pvalue")
            metric = alpha_result.get("metric", "Shannon")
            direction = alpha_result.get("direction", "altered")
            paragraphs.append(
                f"Alpha diversity analysis revealed a significant difference in {metric} diversity between groups "
                f"({_fmt_pvalue(p)}), with {direction} diversity observed in the {alpha_result.get('group_name', 'case')} group."
            )
        else:
            paragraphs.append(
                "No significant differences in alpha diversity metrics were detected between study groups, suggesting comparable within-sample community richness."
            )

        if beta_result:
            p = beta_result.get("pvalue")
            r2 = beta_result.get("r2")
            dist = beta_result.get("distance_metric", "Bray-Curtis")
            paragraphs.append(
                f"Beta-diversity analysis ({dist} distance) demonstrated significant compositional separation between groups "
                f"({_fmt_pvalue(p)}, R² = {r2:.3f}), indicating distinct community structures."
            )
        else:
            paragraphs.append(
                "Beta-diversity ordination showed overlapping clusters between groups, with no statistically significant separation."
            )

        if diff_result:
            n_sig = diff_result.get("n_significant", 0)
            top = diff_result.get("top_feature", "—")
            paragraphs.append(
                f"Differential abundance testing identified {n_sig} taxa with significantly altered abundance after multiple-testing correction. "
                f"The most strongly associated taxon was {top} (log₂FC = {diff_result.get('top_log2fc', '—')}, FDR-adjusted p = {_fmt_pvalue(diff_result.get('top_adj_p'))})."
            )
        else:
            paragraphs.append(
                "No taxa survived multiple-testing correction in the differential abundance analysis."
            )

        for f in findings:
            if isinstance(f, str) and not any(f in p for p in paragraphs):
                paragraphs.append(f)

        content = "\n\n".join(paragraphs)
        return PaperSection(
            section_type="results",
            title="Results",
            content=content,
            word_count=len(content.split()),
        )

    def _write_discussion(self, rs: Dict[str, Any], ctx: Dict[str, Any]) -> PaperSection:
        findings = rs.get("key_findings", [])
        limitations = rs.get("limitations", [
            "This study is observational; causality cannot be inferred.",
            "16S rRNA gene sequencing provides genus-level resolution, limiting strain-level inference.",
            "Residual confounding by diet, medication, or host genetics may influence microbiome composition.",
        ])
        future = rs.get("future_directions", [
            "Longitudinal sampling would clarify temporal dynamics and stability of the observed signatures.",
            "Integration with metabolomics and host transcriptomics would provide mechanistic insight.",
            "Validation in independent cohorts and animal models is needed to establish causality.",
        ])

        content = textwrap.dedent(f"""\
            In this {rs.get('study_design', 'cross-sectional')} study, we profiled the {rs.get('sample_type', 'gut')} microbiome of {rs.get('n_samples', 'N')} participants and identified microbial signatures associated with {rs.get('condition', 'the condition of interest')}. {" ".join(findings[:2])}

            Our findings are consistent with prior reports linking microbiome composition to {rs.get('condition', 'disease phenotype')}, yet they extend the literature by applying rigorous compositional data analysis and controlling for multiple covariates. The use of {rs.get('primary_method', 'standard bioinformatics pipelines')} ensures comparability with recent large-scale initiatives such as the Human Microbiome Project.

            Several limitations warrant consideration. {" ".join(limitations)}

            Looking forward, {" ".join(future)}

            In summary, this work advances our understanding of microbiome–host interactions in {rs.get('condition', 'the studied condition')} and provides a foundation for future mechanistic and translational investigations.
        """)
        return PaperSection(
            section_type="discussion",
            title="Discussion",
            content=content.strip(),
            word_count=len(content.split()),
        )

    def _write_conclusions(self, rs: Dict[str, Any], ctx: Dict[str, Any]) -> PaperSection:
        conclusion = rs.get("conclusion", "Our study identifies reproducible microbiome signatures associated with the condition of interest, highlighting the potential of microbial profiling as a complementary tool in clinical and research settings.")
        content = textwrap.dedent(f"""\
            {conclusion} These results underscore the importance of considering the microbiome as an integral component of host phenotype. Future work should focus on validating these findings in independent populations, elucidating the functional and metabolic mechanisms underlying the observed taxonomic shifts, and exploring the therapeutic potential of microbiome-targeted interventions.
        """)
        return PaperSection(
            section_type="conclusions",
            title="Conclusions",
            content=content.strip(),
            word_count=len(content.split()),
        )

    def _write_keywords(self, rs: Dict[str, Any], ctx: Dict[str, Any]) -> PaperSection:
        kw = rs.get("keywords", ["microbiome", "16S rRNA", "differential abundance", "bioinformatics", "diversity"])
        content = ", ".join(kw)
        return PaperSection(
            section_type="keywords",
            title="Keywords",
            content=content,
            word_count=len(content.split()),
            keywords=kw,
        )

    def _write_generic(self, rs: Dict[str, Any], ctx: Dict[str, Any]) -> PaperSection:
        content = rs.get("content", "No content available for this section type.")
        return PaperSection(
            section_type="generic",
            title="Section",
            content=content,
            word_count=len(content.split()),
        )

    # ------------------------------------------------------------------
    # History helpers
    # ------------------------------------------------------------------

    def _methods_summary_from_history(self) -> str:
        if not self._history:
            return "Standard bioinformatics and statistical methods were employed."
        parts = []
        for rec in self._history[-3:]:
            method = rec.get("method", "analysis")
            parts.append(method.replace("_", " "))
        return f"Analyses included {', '.join(parts)}."

    def _stats_methods_from_history(self) -> str:
        if not self._history:
            return "Alpha diversity was compared using the Wilcoxon rank-sum test; beta diversity was assessed by PERMANOVA on Bray-Curtis distances; differential abundance was evaluated with DESeq2."
        parts = []
        method_map = {
            "alpha_diversity": "Alpha diversity metrics were compared using non-parametric tests (Wilcoxon / Kruskal-Wallis).",
            "permanova": "Community compositional differences were tested by PERMANOVA on Bray-Curtis and weighted UniFrac distances.",
            "lefse": "Differential taxa were identified with LEfSe (LDA > 2.0).",
            "ancom": "ANCOM was used for compositional differential abundance testing.",
            "deseq2": "DESeq2 was applied to raw counts with shrinkage estimation.",
            "aldex2": "ALDEx2 provided robust differential abundance estimates via centred log-ratio transformation.",
            "maaslin2": "MaAsLin2 fitted multivariable linear models on TSS-normalised data.",
            "pcoa": "PCoA visualised beta-diversity patterns.",
            "nmds": "NMDS was used as a non-metric alternative for ordination.",
            "correlation": "Correlations were computed using SparCC or Spearman's rank method.",
            "network": "Co-occurrence networks were inferred and modularity was assessed.",
            "functional": "Functional potential was inferred using HUMAnN 3 and pathway abundances were tested with MaAsLin2.",
            "mixed_effects_alpha": "Linear mixed-effects models accounted for repeated measures.",
        }
        seen = set()
        for rec in self._history:
            m = rec.get("method", "")
            desc = method_map.get(m)
            if desc and m not in seen:
                parts.append(desc)
                seen.add(m)
        return " ".join(parts) if parts else method_map.get("alpha_diversity", "")


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator – AgentEngine
# ──────────────────────────────────────────────────────────────────────────────

class AgentEngine:
    """
    Main orchestration engine that wires together L3, L4, and L5 sub-engines.
    L1 (query parsing) and L2 (data awareness) are handled upstream.
    """

    def __init__(self):
        self.method_recommender = MethodRecommender()
        self.result_interpreter = ResultInterpreter()
        self.enhanced_interpreter = EnhancedInterpreter()
        self.paper_writer = PaperWriter()

    # ------------------------------------------------------------------
    # L3 – Method recommendation
    # ------------------------------------------------------------------

    def recommend_methods(
        self,
        data_summary: Dict[str, Any],
        research_question: str,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        Given data characteristics and a research question, return a ranked
        list of recommended analysis methods with justifications.
        """
        recommendations = self.method_recommender.recommend(
            data_summary, research_question, top_k=top_k
        )
        return {
            "recommendations": [
                {
                    "method": r.method,
                    "category": r.category,
                    "confidence": r.confidence,
                    "justification": r.justification,
                    "prerequisites": r.prerequisites,
                    "contraindications": r.contraindications,
                    "typical_runtime": r.typical_runtime,
                    "suggested_parameters": r.suggested_parameters,
                }
                for r in recommendations
            ],
            "query": research_question,
            "data_type": data_summary.get("data_type"),
            "sample_size": data_summary.get("sample_size"),
            "study_design": data_summary.get("study_design"),
        }

    # ------------------------------------------------------------------
    # L4 – Result interpretation
    # ------------------------------------------------------------------

    def interpret_results(
        self,
        analysis_type: str,
        statistics: Dict[str, Any],
        plot_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate natural-language interpretation of analysis results.
        """
        interp = self.result_interpreter.interpret(
            analysis_type=analysis_type,
            statistics=statistics,
            plot_data=plot_data,
        )
        return {
            "analysis_type": analysis_type,
            "summary": interp.summary,
            "detailed": interp.detailed,
            "clinical_relevance": interp.clinical_relevance,
            "caveats": interp.caveats,
            "follow_up_suggestions": interp.follow_up_suggestions,
        }

    def interpret_full_results(
        self,
        all_results: Dict[str, Any],
        metadata_summary: Optional[Dict[str, Any]] = None,
        question: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cross-analysis integrated interpretation using knowledge base.
        Optional LLM enhancement for narrative quality.
        """
        interp = self.enhanced_interpreter.interpret_full(
            all_results=all_results,
            metadata_summary=metadata_summary,
            question=question,
        )
        return {
            "integrated_narrative": interp.integrated_narrative,
            "biological_context": interp.biological_context,
            "caveats": interp.caveats,
            "follow_up_suggestions": interp.follow_up_suggestions,
            "contradictions": interp.contradictions,
            "disease_relevance": interp.disease_relevance,
            "llm_enhanced": interp.llm_enhanced,
            "llm_model": interp.llm_model,
        }

    # ------------------------------------------------------------------
    # L5 – Paper writing
    # ------------------------------------------------------------------

    def write_paper_section(
        self,
        section_type: str,
        results_summary: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a publication-ready manuscript section.
        """
        section = self.paper_writer.write_section(
            section_type=section_type,
            results_summary=results_summary,
            context=context,
        )
        return {
            "section_type": section.section_type,
            "title": section.title,
            "content": section.content,
            "word_count": section.word_count,
            "keywords": section.keywords,
        }

    def write_full_paper(
        self,
        results_summary: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate all standard manuscript sections at once.
        """
        sections = self.paper_writer.write_full_paper(results_summary, context)
        return {
            "title": results_summary.get("title", context.get("study_name", "Untitled") if context else "Untitled"),
            "sections": {
                name: {
                    "section_type": s.section_type,
                    "title": s.title,
                    "content": s.content,
                    "word_count": s.word_count,
                    "keywords": s.keywords,
                }
                for name, s in sections.items()
            },
        }

    # ------------------------------------------------------------------
    # Convenience – build paper from analysis history
    # ------------------------------------------------------------------

    def build_paper_from_history(
        self,
        history: List[Dict[str, Any]],
        study_metadata: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        High-level helper: feed a list of completed analysis records into the
        PaperWriter history, then generate a full manuscript draft.
        """
        for rec in history:
            self.paper_writer.add_analysis_record(rec)
        return self.write_full_paper(study_metadata, context)
