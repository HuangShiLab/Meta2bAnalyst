"""
Agent Planner
=============
Converts natural language user requests into structured execution plans.

Two modes:
1. Rule Engine (default): Keyword/template matching - works offline, no API key needed
2. LLM Mode: OpenAI/Anthropic GPT planner - requires API key, more flexible

The planner outputs a JSON DAG (Directed Acyclic Graph) where each node is
an analysis step with module name, parameters, and dependencies.
"""
import json
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from app.agent.module_registry import MODULE_REGISTRY, get_module_spec, get_module_names

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """A single step in the execution plan."""
    id: str
    module: str
    params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ExecutionPlan:
    """Complete execution plan as a DAG.

    ``clarification_needed`` is set when the planner could not work out which
    analysis the user wants. In that case the plan carries no analysis steps and
    the caller must ask the user to rephrase instead of pretending that a
    validator-only plan is a real analysis.
    """
    query: str
    steps: List[PlanStep]
    estimated_time: str = ""
    notes: List[str] = field(default_factory=list)
    clarification_needed: bool = False


# ───────────────────────────────────────────────────────────────
# TEMPLATES (Rule Engine)
# ───────────────────────────────────────────────────────────────

ANALYSIS_TEMPLATES = [
    {
        "name": "full_multiomics_pipeline",
        "patterns": [
            r"full.*multi.?omics|complete.*pipeline|run.*all.*analysis|integrat.*everything",
            r"全部.*分析|完整.*流程|多组学.*整合.*全部",
        ],
        "description": "Complete multi-omics pipeline: individual profiling + integration + markers + report",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "microbiome_pcoa", "id": "step2_mb_pcoa", "depends_on": ["step1_validate"]},
            {"module": "metabolome_pca", "id": "step3_met_pca", "depends_on": ["step1_validate"]},
            {"module": "permanova", "id": "step4_permanova_mb", "depends_on": ["step2_mb_pcoa"], "params": {"data_type": "microbiome"}},
            {"module": "permanova", "id": "step5_permanova_met", "depends_on": ["step3_met_pca"], "params": {"data_type": "metabolome"}},
            {"module": "microbiome_marker", "id": "step6_mb_marker", "depends_on": ["step1_validate"]},
            {"module": "metabolome_marker", "id": "step7_met_marker", "depends_on": ["step1_validate"]},
            {"module": "procrustes", "id": "step8_procrustes", "depends_on": ["step2_mb_pcoa", "step3_met_pca"]},
            {"module": "mantel_test", "id": "step9_mantel", "depends_on": ["step1_validate"]},
            {"module": "sparse_cca", "id": "step10_scca", "depends_on": ["step1_validate"]},
            {"module": "cross_correlation", "id": "step11_crosscorr", "depends_on": ["step1_validate"]},
            {"module": "report_generator", "id": "step12_report", "depends_on": ["step2_mb_pcoa", "step3_met_pca", "step4_permanova_mb", "step5_permanova_met", "step6_mb_marker", "step7_met_marker", "step8_procrustes", "step9_mantel"]},
        ],
    },
    {
        "name": "individual_omics_profiling",
        "patterns": [
            r"individual.*omics|profil.*each|separate.*analysis|microbiome.*and.*metabolome.*separately",
            r"分别.*分析|各自.*分析|单独.*分析",
        ],
        "description": "Profile microbiome and metabolome separately with PCoA, PCA, PERMANOVA",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "microbiome_pcoa", "id": "step2_mb_pcoa", "depends_on": ["step1_validate"]},
            {"module": "metabolome_pca", "id": "step3_met_pca", "depends_on": ["step1_validate"]},
            {"module": "permanova", "id": "step4_permanova_mb", "depends_on": ["step2_mb_pcoa"], "params": {"data_type": "microbiome"}},
            {"module": "permanova", "id": "step5_permanova_met", "depends_on": ["step3_met_pca"], "params": {"data_type": "metabolome"}},
        ],
    },
    {
        "name": "marker_discovery",
        "patterns": [
            r"marker.*discover|differential.*abundance|diff.*analysis|biomarker|significant.*feature",
            # Ordinary phrasings: "find differential markers comparing visits",
            # "which markers differ between groups", "differentially abundant taxa".
            r"differential.*(marker|feature|taxa|genera|genus|specie|metabolite)",
            r"(find|identify|discover|show|list|get).*\bmarkers?\b",
            r"\bmarkers?\b.*(between|across|comparing|compare|by group|discovery)",
            r"differential(ly)?.*(analysis|abundant|expressed)",
            r"标记物|差异.*分析|差异.*代谢物|差异.*菌|差异.*标记|差异.*特征|差异.*物种",
        ],
        "description": "Marker discovery for both microbiome (CLR+Wilcoxon) and metabolome (log1p+Welch)",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "microbiome_marker", "id": "step2_mb_marker", "depends_on": ["step1_validate"]},
            {"module": "metabolome_marker", "id": "step3_met_marker", "depends_on": ["step1_validate"]},
            {"module": "report_generator", "id": "step4_report", "depends_on": ["step2_mb_marker", "step3_met_marker"]},
        ],
    },
    {
        "name": "procrustes_mantel",
        "patterns": [
            r"procrustes|mantel|align.*microbiome.*metabolome|compare.*ordination",
            r"procrustes|mantel|对齐.*微生物组.*代谢组",
        ],
        "description": "Procrustes alignment and Mantel test for microbiome-metabolome integration",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "microbiome_pcoa", "id": "step2_mb_pcoa", "depends_on": ["step1_validate"]},
            {"module": "metabolome_pca", "id": "step3_met_pca", "depends_on": ["step1_validate"]},
            {"module": "procrustes", "id": "step4_procrustes", "depends_on": ["step2_mb_pcoa", "step3_met_pca"]},
            {"module": "mantel_test", "id": "step5_mantel", "depends_on": ["step1_validate"]},
        ],
    },
    {
        "name": "sparse_cca_rda_o2pls",
        "patterns": [
            r"sparse.*cca|scca|rda|o2pls|canonical.*correlation|redundancy.*analysis",
            r"稀疏.*cca|rda|o2pls|典型.*相关",
        ],
        "description": "Advanced multi-omics integration: Sparse CCA, RDA, and O2PLS",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "sparse_cca", "id": "step2_scca", "depends_on": ["step1_validate"]},
            {"module": "rda", "id": "step3_rda", "depends_on": ["step1_validate"]},
            {"module": "o2pls", "id": "step4_o2pls", "depends_on": ["step1_validate"]},
        ],
    },
    {
        "name": "cross_correlation",
        "patterns": [
            r"cross.*correlation|correlat.*genera.*metabolite|heatmap.*genus.*metabolite",
            r"correlat\w*\s+(the\s+)?(genera|genus|taxa|microbe\w*|bacteri\w*|species)\b",
            r"(genera|genus|taxa|microbe\w*|bacteri\w*)\b.*\b(with|and|against|vs\.?|versus)\b.*metabolit",
            r"交叉.*相关|菌属.*代谢物.*相关|热图.*相关|菌.*代谢物.*关联",
        ],
        "description": "Spearman cross-correlation between bacterial genera and metabolites",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "cross_correlation", "id": "step2_crosscorr", "depends_on": ["step1_validate"]},
        ],
    },
    {
        "name": "network_analysis",
        "patterns": [
            r"network|sparcc|correlation.*network|co.?occurrence",
            r"网络|共现|相关性.*网络",
        ],
        "description": "SparCC correlation network for microbiome taxa",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "network_sparcc", "id": "step2_network", "depends_on": ["step1_validate"]},
        ],
    },
    {
        "name": "pathway_analysis",
        "patterns": [
            r"pathway|kegg|enrichment|functional.*analysis",
            r"通路|kegg|富集.*分析|功能.*分析",
        ],
        "description": "KEGG pathway enrichment and functional prediction",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "pathway_kegg", "id": "step2_pathway", "depends_on": ["step1_validate"]},
            {"module": "functional_prediction", "id": "step3_picrust", "depends_on": ["step1_validate"]},
        ],
    },
    {
        "name": "alpha_diversity",
        "patterns": [
            r"alpha.*diversit|richness|shannon|simpson",
            r"alpha.*多样性|丰富度|香农|辛普森",
        ],
        "description": "Alpha diversity analysis for both microbiome and metabolome",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "microbiome_alpha", "id": "step2_mb_alpha", "depends_on": ["step1_validate"]},
            {"module": "metabolome_alpha", "id": "step3_met_alpha", "depends_on": ["step1_validate"]},
        ],
    },
    {
        "name": "dimensionality_reduction",
        "patterns": [
            r"tsne|umap|t-sne|dimension.*reduction",
            r"tsne|umap|降维|维度.*降低",
        ],
        "description": "Advanced dimensionality reduction with t-SNE and UMAP",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "tsne", "id": "step2_tsne", "depends_on": ["step1_validate"], "params": {"data_type": "microbiome"}},
            {"module": "umap", "id": "step3_umap", "depends_on": ["step1_validate"], "params": {"data_type": "microbiome"}},
        ],
    },
    {
        "name": "auto_analyze",
        "patterns": [
            r"analyze.*data|help.*analyze|analyze.*for.*me|run.*analysis|帮我分析|分析.*数据|自动分析",
            r"what.*can.*do|recommend|suggest.*analysis|应该.*分析",
        ],
        "description": "Auto-detect data type and recommend appropriate analysis pipeline",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "microbiome_pcoa", "id": "step2_mb_pcoa", "depends_on": ["step1_validate"]},
            {"module": "permanova", "id": "step3_permanova", "depends_on": ["step2_mb_pcoa"], "params": {"data_type": "microbiome"}},
            {"module": "microbiome_alpha", "id": "step4_mb_alpha", "depends_on": ["step1_validate"]},
            {"module": "microbiome_marker", "id": "step5_mb_marker", "depends_on": ["step1_validate"]},
            {"module": "network_sparcc", "id": "step6_network", "depends_on": ["step1_validate"]},
        ],
    },
    # ── Research Question Templates ──
    {
        "name": "group_effect_question",
        "patterns": [
            r"treatment.*affect|group.*effect|disease.*affect|分组.*影响|治疗.*影响|疾病.*影响",
            r"does.*treatment|does.*group|is.*there.*difference.*between",
        ],
        "description": "Test whether grouping variable affects microbiome/metabolome composition",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "microbiome_pcoa", "id": "step2_mb_pcoa", "depends_on": ["step1_validate"]},
            {"module": "permanova", "id": "step3_permanova", "depends_on": ["step2_mb_pcoa"], "params": {"data_type": "microbiome"}},
            {"module": "anosim", "id": "step4_anosim", "depends_on": ["step1_validate"]},
        ],
    },
    {
        "name": "association_question",
        "patterns": [
            r"associated.*with|correlated.*with|related.*to|相关|关联",
            r"which.*bacteria.*disease|which.*taxa.*group|what.*features.*associated",
            r"biomarker.*for|marker.*for|indicator.*of",
        ],
        "description": "Find features associated with a phenotype or grouping variable",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "microbiome_marker", "id": "step2_mb_marker", "depends_on": ["step1_validate"]},
            {"module": "random_forest", "id": "step3_rf", "depends_on": ["step1_validate"]},
            {"module": "volcano", "id": "step4_volcano", "depends_on": ["step2_mb_marker"]},
        ],
    },
    {
        "name": "integration_question",
        "patterns": [
            r"microbiome.*metabolome.*correlated|microbiome.*metabolome.*related",
            r"integrat.*microbiome.*metabolome|关联.*微生物组.*代谢组",
            r"two.*omics.*together|multi.*omics.*integrat",
        ],
        "description": "Integrate microbiome and metabolome data to find cross-omics associations",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "microbiome_pcoa", "id": "step2_mb_pcoa", "depends_on": ["step1_validate"]},
            {"module": "metabolome_pca", "id": "step3_met_pca", "depends_on": ["step1_validate"]},
            {"module": "procrustes", "id": "step4_procrustes", "depends_on": ["step2_mb_pcoa", "step3_met_pca"]},
            {"module": "mantel_test", "id": "step5_mantel", "depends_on": ["step1_validate"]},
            {"module": "cross_correlation", "id": "step6_crosscorr", "depends_on": ["step1_validate"]},
        ],
    },
    {
        "name": "temporal_question",
        "patterns": [
            r"change.*over.*time|temporal.*change|longitudinal|time.*series",
            r"随时间.*变化|纵向.*分析|时间.*序列",
            r"how.*does.*change.*over|trajectory.*analysis",
        ],
        "description": "Analyze microbiome changes over time or across timepoints",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
            {"module": "microbiome_pcoa", "id": "step2_mb_pcoa", "depends_on": ["step1_validate"]},
            {"module": "permanova", "id": "step3_permanova", "depends_on": ["step2_mb_pcoa"], "params": {"data_type": "microbiome"}},
            {"module": "maaslin3", "id": "step4_maaslin", "depends_on": ["step1_validate"]},
        ],
    },
    {
        "name": "method_recommendation",
        "patterns": [
            r"what.*method|which.*test|what.*analysis|should.*use|推荐.*方法",
            r"appropriate.*method|suitable.*test|best.*method|用什么方法",
            r"longitudinal.*method|compositional.*method|paired.*method",
        ],
        "description": "Recommend appropriate statistical methods based on data characteristics",
        "steps": [
            {"module": "data_validator", "id": "step1_validate"},
        ],
        # Advisory templates deliberately plan no analysis steps - the answer is a
        # method recommendation (see /agent/recommend), not a DAG. Flagged so the
        # validator-only plan is never presented as if it were an analysis.
        "advisory": True,
        "notes": ["This is a method recommendation request. The Agent will provide method suggestions based on data characteristics."],
    },
]




# ───────────────────────────────────────────────────────────────
# DATA-AWARE PLANNING
# ───────────────────────────────────────────────────────────────

def _infer_data_type_from_files(file_list: List[str]) -> Dict[str, Any]:
    """Infer data types from uploaded file names/extensions."""
    data_types = {
        "has_microbiome": False,
        "has_metabolome": False,
        "has_metaphlan": False,
        "has_humann3": False,
        "has_metadata": False,
        "format": "unknown",
    }
    
    for fname in file_list:
        fname_lower = fname.lower()
        if any(k in fname_lower for k in ['metaphlan', 'clade_name']):
            data_types["has_metaphlan"] = True
            data_types["has_microbiome"] = True
        if any(k in fname_lower for k in ['humann3', 'humann', 'genefamilies', 'pathabundance']):
            data_types["has_humann3"] = True
        if any(k in fname_lower for k in ['microbiome', '16s', 'otu', 'asv', 'species', 'feature_table']):
            data_types["has_microbiome"] = True
        if any(k in fname_lower for k in ['metabolome', 'metabolite', 'lcms', 'gcms']):
            data_types["has_metabolome"] = True
        if any(k in fname_lower for k in ['metadata', 'meta', 'sample']):
            data_types["has_metadata"] = True
    
    # Determine format
    if data_types["has_metaphlan"]:
        data_types["format"] = "metaphlan"
    elif data_types["has_humann3"]:
        data_types["format"] = "humann3"
    elif data_types["has_microbiome"] and data_types["has_metabolome"]:
        data_types["format"] = "multiomics"
    elif data_types["has_microbiome"]:
        data_types["format"] = "microbiome"
    elif data_types["has_metabolome"]:
        data_types["format"] = "metabolome"
    
    return data_types


def _get_recommended_steps(data_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get recommended analysis steps based on detected data types."""
    steps = [{"module": "data_validator", "id": "step1_validate"}]
    step_num = 2
    
    if data_info["has_metaphlan"]:
        # MetaPhlAn data: PCoA, alpha, markers, network, pathway (from species)
        steps.append({"module": "microbiome_pcoa", "id": f"step{step_num}_mb_pcoa", "depends_on": ["step1_validate"]})
        step_num += 1
        steps.append({"module": "microbiome_alpha", "id": f"step{step_num}_mb_alpha", "depends_on": ["step1_validate"]})
        step_num += 1
        steps.append({"module": "permanova", "id": f"step{step_num}_permanova", "depends_on": [f"step{step_num-2}_mb_pcoa"], "params": {"data_type": "microbiome"}})
        step_num += 1
        steps.append({"module": "microbiome_marker", "id": f"step{step_num}_mb_marker", "depends_on": ["step1_validate"]})
        step_num += 1
        steps.append({"module": "network_sparcc", "id": f"step{step_num}_network", "depends_on": ["step1_validate"]})
        step_num += 1
    
    if data_info["has_humann3"]:
        # HUMAnN3 data: functional PCA, pathway analysis, functional markers
        steps.append({"module": "functional_prediction", "id": f"step{step_num}_func", "depends_on": ["step1_validate"]})
        step_num += 1
        steps.append({"module": "pathway_kegg", "id": f"step{step_num}_pathway", "depends_on": ["step1_validate"]})
        step_num += 1
    
    if data_info["has_microbiome"] and not data_info["has_metaphlan"]:
        # Standard microbiome (16S)
        steps.append({"module": "microbiome_pcoa", "id": f"step{step_num}_mb_pcoa", "depends_on": ["step1_validate"]})
        step_num += 1
        steps.append({"module": "microbiome_alpha", "id": f"step{step_num}_mb_alpha", "depends_on": ["step1_validate"]})
        step_num += 1
        steps.append({"module": "permanova", "id": f"step{step_num}_permanova", "depends_on": [f"step{step_num-2}_mb_pcoa"], "params": {"data_type": "microbiome"}})
        step_num += 1
        steps.append({"module": "microbiome_marker", "id": f"step{step_num}_mb_marker", "depends_on": ["step1_validate"]})
        step_num += 1
        steps.append({"module": "network_sparcc", "id": f"step{step_num}_network", "depends_on": ["step1_validate"]})
        step_num += 1
    
    if data_info["has_metabolome"]:
        steps.append({"module": "metabolome_pca", "id": f"step{step_num}_met_pca", "depends_on": ["step1_validate"]})
        step_num += 1
        steps.append({"module": "metabolome_marker", "id": f"step{step_num}_met_marker", "depends_on": ["step1_validate"]})
        step_num += 1
    
    if data_info["has_microbiome"] and data_info["has_metabolome"]:
        # Multi-omics integration
        steps.append({"module": "procrustes", "id": f"step{step_num}_procrustes", "depends_on": [f"step{step_num-4}_mb_pcoa" if data_info['has_microbiome'] else "step1_validate", f"step{step_num-2}_met_pca"]})
        step_num += 1
        steps.append({"module": "mantel_test", "id": f"step{step_num}_mantel", "depends_on": ["step1_validate"]})
        step_num += 1
    
    return steps

# ───────────────────────────────────────────────────────────────
# KEYWORD-BASED MODULE DETECTION
# ───────────────────────────────────────────────────────────────

MODULE_KEYWORDS = {
    # Community Structure
    "microbiome_pcoa": ["pcoa", "bray-curtis", "principal coordinate", "microbiome.*ordination", "微生物组.*pcoa", "bray", "ordination"],
    "metabolome_pca": ["pca", "principal component", "metabolome.*pca", "代谢组.*pca", "代谢物.*主成分", "pca.*metabolome"],
    "microbiome_nmds": ["nmds", "non-metric", "multidimensional.*scaling"],
    "tsne": ["tsne", "t-sne", "tsne.*plot"],
    "umap": ["umap", "uniform.*manifold"],
    "permanova": ["permanova", "adonis", "metadata.*effect", "分组.*效应", "置换.*方差", "group.*effect", "treatment.*effect"],
    "anosim": ["anosim", "analysis.*similarities"],
    "microbiome_alpha": ["alpha.*diversit", "richness", "shannon", "simpson", "pielou", "alpha diversity"],
    "metabolome_alpha": ["metabolome.*alpha", "metabolite.*richness"],
    
    # Differential Analysis
    "microbiome_marker": ["microbiome.*marker", "microbiome.*differential", "clr.*wilcoxon", "微生物组.*标记", "微生物组.*差异", "differential.*abundance", "biomarker", "biomarker.*discovery", "marker.*discovery", "significant.*taxa", "significant.*feature", "differential.*marker", "diff.*taxa", "差异.*标记", "标记.*发现"],
    "metabolome_marker": ["metabolome.*marker", "metabolome.*differential", "代谢组.*标记", "代谢物.*差异", "differential.*metabolite"],
    "maaslin3": ["maaslin", "multivariate.*association", "mixed.*effect", "longitudinal.*analysis", "纵向.*分析", "重复.*测量"],
    
    # Machine Learning
    "random_forest": ["random.*forest", "rf.*importance", "feature.*importance", "机器学习", "randomforest"],
    
    # Network
    "network_sparcc": ["network", "sparcc", "网络", "共现", "co-occurrence", "co.*occurrence", "correlation.*network"],
    
    # Functional
    "pathway_kegg": ["pathway", "kegg", "通路", "富集", "pathway.*enrichment", "enrichment.*analysis"],
    "functional_prediction": ["picrust", "picrust2", "tax4fun", "piphillin", "functional.*prediction", "功能.*预测", "gene.*prediction"],
    
    # Integration
    "procrustes": ["procrustes", "对齐", "alignment"],
    "mantel_test": ["mantel", "距离.*相关", "distance.*correlation"],
    "cross_site_permanova": ["cross.?site.*(variance|permanova|explain)", "位点.*解释", "跨位点.*方差",
                             "explained variance.*site", "多位点.*解释"],
    "cross_omics_gbdt": ["gbdt", "gradient boost", "predict.*metabolite.*(micro|taxa|genus)",
                         "特征.*可重复性", "nested.*cv", "预测.*代谢物"],
    "cross_site_network": ["cross.?site.*network", "位点.*网络", "跨位点.*关联.*网络",
                           "shared.*(metabolite|target)", "hub.*genus"],
    "cross_site_concordance": ["concordan", "同向", "跨位点.*(一致|同向)", "多位点.*共同.*(富集|关联)",
                               "consistent.*direction.*site"],
    "sparse_cca": ["sparse.*cca", "scca", "canonical", "典型.*相关"],
    "rda": ["rda", "redundancy", "冗余.*分析"],
    "o2pls": ["o2pls", "joint.*variation", "orthogonal"],
    "cross_correlation": ["cross.*correlation", "heatmap", "genus.*metabolite", "菌属.*代谢物"],
    # NOTE: key was "moafa" (typo), so MOFA+ queries never routed anywhere. The
    # pattern also used "mofa\+" in a non-raw string, an invalid escape sequence.
    "mofa": ["mofa", r"mofa\+", "factor.*analysis", "multi-omics.*factor"],
    "diablo": ["diablo", "spls-da", "pls-da", "mixomics"],
    "wgcna": ["wgcna", "weighted.*co-expression", "module.*detection", "module.*analysis"],
    
    # Phylogenetic
    "unifrac": ["unifrac", "weighted.*unifrac", "unweighted.*unifrac", "phylogenetic.*distance"],
    
    # Strain/Source
    "strain_analyzer": ["strain", "ani", "strain.*analysis", "菌株"],
    "source_tracking": ["feast", "source.*track", "溯源", "source.*contribution"],
    
    # Report
    "report_generator": ["report", "pdf", "报告", "generate.*report", "export.*pdf"],
    
    # Visualization
    "taxonomy_bar": ["bar.*plot", "stacked.*bar", "taxonomy.*bar", "composition.*plot", "物种.*组成", "堆叠.*柱状图"],
    "rarefaction": ["rarefaction", "rarefaction.*curve", "sequencing.*depth", "稀疏.*曲线", "测序.*深度"],
    "volcano": ["volcano", "volcano.*plot", "火山.*图"],
    "heatmap": ["heatmap", "heat.*map", "热图"],
    "upset": ["upset", "upset.*plot", "intersection.*plot"],
    
    # Enterotype
    "enterotype": ["enterotype", "肠型", "dirichlet.*multinomial", "dmm", "cluster.*microbiome"],
    
    # ALDEx2 / Songbird
    "aldex2": ["aldex2", "aldex", "compositional.*test"],
    "songbird": ["songbird", "qurro", "differential.*rank"],
}


def _match_template(query: str) -> Optional[Dict[str, Any]]:
    """Match query against predefined templates using regex patterns.

    The template whose patterns match the query most often wins; ties are broken
    by declaration order, so a query that matches exactly one template behaves
    the same as it did under first-match-wins.
    """
    query_lower = query.lower()
    scored: List[Tuple[int, int, Dict[str, Any]]] = []
    for idx, template in enumerate(ANALYSIS_TEMPLATES):
        hits = sum(
            1 for pattern in template["patterns"]
            if re.search(pattern, query_lower, re.IGNORECASE)
        )
        if hits:
            scored.append((hits, idx, template))
    if not scored:
        return None
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[0][2]


def unregistered_keyword_modules() -> List[str]:
    """MODULE_KEYWORDS keys that have no entry in MODULE_REGISTRY.

    Keyword routing and the module registry are maintained by hand and had
    drifted apart ("moafa", "diablo", "wgcna", "random_forest" were routable but
    not registered), so a matching query produced a plan step the executor could
    not resolve.

    These keys are deliberately *kept* in MODULE_KEYWORDS: a query for one of
    them is recognised as "you asked for X, X is not available yet" (see
    ``_detect_modules_from_keywords``) rather than being silently ignored. A
    module only becomes plannable once it has BOTH a ModuleSpec here and an
    entry in ``app.agent.executor._MODULE_FUNCTIONS`` - see
    ``module_registry.PENDING_EXECUTOR_WIRING``.
    """
    return sorted(set(MODULE_KEYWORDS) - set(MODULE_REGISTRY))


# Log the drift once at import instead of on every planning call.
_PENDING_KEYWORD_MODULES = unregistered_keyword_modules()
if _PENDING_KEYWORD_MODULES:
    logger.warning(
        "%d keyword rule(s) route to modules with no MODULE_REGISTRY entry and "
        "are therefore not plannable: %s",
        len(_PENDING_KEYWORD_MODULES),
        ", ".join(_PENDING_KEYWORD_MODULES),
    )


def _detect_modules_from_keywords(query: str) -> Tuple[List[Tuple[str, float]], List[str]]:
    """Detect individual modules mentioned in query with confidence scores.

    Returns ``(matched, unavailable)`` where ``matched`` holds only modules that
    exist in MODULE_REGISTRY (anything else would yield a step the executor
    cannot resolve) and ``unavailable`` holds the names the query asked for that
    are not implemented yet, so the planner can say so out loud.
    """
    query_lower = query.lower()
    matched: List[Tuple[str, float]] = []
    unavailable: List[str] = []
    for module_name, keywords in MODULE_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if re.search(kw, query_lower, re.IGNORECASE):
                score += 1
        if not score:
            continue
        if module_name not in MODULE_REGISTRY:
            unavailable.append(module_name)
            continue
        matched.append((module_name, score))
    # Sort by confidence (stable: ties keep MODULE_KEYWORDS declaration order)
    matched.sort(key=lambda x: x[1], reverse=True)
    return matched, unavailable


def _infer_data_type(query: str) -> Dict[str, bool]:
    """Infer which omics data types the query explicitly mentions.

    ``explicit`` is False when the query names neither omics ("find differential
    markers comparing visits"). In that case both flags are True so the planner
    does NOT drop every microbiome/metabolome module and collapse to a
    validator-only plan; what is actually available is decided later from the
    session context (see ``_available_omics_from_context``).
    """
    q = query.lower()
    has_mb = any(k in q for k in ["microbiome", "microbial", "16s", "bacteria", "taxa", "genus", "genera", "微生物组", "菌群", "细菌"])
    has_met = any(k in q for k in ["metabolome", "metabolite", "metabolic", "lc-ms", "代谢组", "代谢物"])
    if not has_mb and not has_met:
        return {"microbiome": True, "metabolome": True, "explicit": False}
    return {"microbiome": has_mb, "metabolome": has_met, "explicit": True}


def _available_omics_from_context(context: Optional[Dict[str, Any]]) -> Optional[str]:
    """Work out which omics the session actually holds.

    Returns 'microbiome_only', 'metabolome_only' or None (both / unknown).
    An explicit ``context['available_data']`` wins; otherwise it is derived from
    the uploaded file names and file types so the planner does not schedule
    steps that are guaranteed to fail for lack of data.
    """
    if not context:
        return None
    explicit = context.get("available_data")
    if explicit in ("microbiome_only", "metabolome_only"):
        return explicit
    names = list(context.get("session_files") or []) + [
        str(t) for t in (context.get("file_types") or [])
    ]
    if not names:
        return None
    info = _infer_data_type_from_files(names)
    if info["has_microbiome"] and not info["has_metabolome"]:
        return "microbiome_only"
    if info["has_metabolome"] and not info["has_microbiome"]:
        return "metabolome_only"
    return None


def _drop_unrunnable_steps(steps: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Remove steps whose module is not in MODULE_REGISTRY and repair the DAG.

    Some templates reference modules that are not registered/executable yet
    (anosim, random_forest, volcano). Keeping them would produce a plan the
    executor aborts on; dropping them naively would leave dangling depends_on
    entries that stall every downstream step. Dependencies on a dropped step are
    therefore rewired to that step's own dependencies.
    """
    kept: List[Dict[str, Any]] = []
    dropped_deps: Dict[str, List[str]] = {}
    dropped_modules: List[str] = []

    for step in steps:
        if step["module"] in MODULE_REGISTRY:
            kept.append(step)
        else:
            dropped_deps[step["id"]] = list(step.get("depends_on", []))
            if step["module"] not in dropped_modules:
                dropped_modules.append(step["module"])

    if dropped_modules:
        for step in kept:
            resolved: List[str] = []
            seen_dropped: set = set()
            stack = list(step.get("depends_on", []))
            while stack:
                dep = stack.pop(0)
                if dep in dropped_deps:
                    if dep in seen_dropped:
                        continue
                    seen_dropped.add(dep)
                    stack.extend(dropped_deps[dep])
                elif dep not in resolved:
                    resolved.append(dep)
            step["depends_on"] = resolved

    return kept, dropped_modules


def _prune_dangling_dependencies(steps: List[PlanStep]) -> None:
    """Drop depends_on entries pointing at steps that are no longer in the plan.

    Without this, filtering a plan (e.g. removing metabolome steps for a
    microbiome-only session) leaves survivors waiting on a step that will never
    run, and the executor silently skips them.
    """
    valid = {s.id for s in steps}
    for step in steps:
        step.depends_on = [d for d in step.depends_on if d in valid]


def _apply_best_practices(plan_steps: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """Apply domain best practices to the plan."""
    q = query.lower()
    steps = [dict(s) for s in plan_steps]

    # Auto-inject data_validator if not present
    if not any(s["module"] == "data_validator" for s in steps):
        steps.insert(0, {"module": "data_validator", "id": "step0_validate"})
        # Update dependencies
        for s in steps[1:]:
            if not s.get("depends_on"):
                s["depends_on"] = ["step0_validate"]

    # Ensure microbiome_marker uses CLR + Wilcoxon
    for s in steps:
        if s["module"] == "microbiome_marker":
            s.setdefault("params", {})
            s["params"]["transformation"] = "clr"
            s["params"]["test_method"] = "mannwhitney"

    # Ensure metabolome_marker uses log1p + Welch
    for s in steps:
        if s["module"] == "metabolome_marker":
            s.setdefault("params", {})
            s["params"]["transformation"] = "log1p"
            s["params"]["test_method"] = "welch"

    # Auto-add reference_group if comparing to baseline
    if any(k in q for k in ["day 0", "baseline", "reference", "control", "t4", "vs"]):
        for s in steps:
            if s["module"] in ("microbiome_marker", "metabolome_marker"):
                s.setdefault("params", {})
                if "reference_group" not in s["params"]:
                    s["params"]["reference_group"] = "T4"

    # Auto-inject group_column
    for s in steps:
        if s["module"] in ("permanova", "microbiome_marker", "metabolome_marker",
                           "microbiome_pcoa", "metabolome_pca", "microbiome_alpha", "metabolome_alpha"):
            s.setdefault("params", {})
            if "group_column" not in s["params"]:
                s["params"]["group_column"] = "Visit"

    # Add report_generator for complete pipelines
    if len(steps) >= 3 and not any(s["module"] == "report_generator" for s in steps):
        # Check if user asked for a report
        if any(k in q for k in ["report", "pdf", "报告", "生成", "output"]):
            all_ids = [s["id"] for s in steps]
            steps.append({
                "module": "report_generator",
                "id": f"step{len(steps)+1}_report",
                "depends_on": all_ids[-3:],  # depend on last 3 steps
                "params": {"format": "pdf"},
            })

    return steps


def _estimate_time(n_steps: int) -> str:
    """Rough wall-clock estimate for a plan of n_steps."""
    if n_steps > 8:
        return f"~{(n_steps * 15) // 60}-{(n_steps * 15 + 60) // 60} minutes"
    return f"~{n_steps * 15}-{(n_steps * 15) + 30} seconds"


CLARIFICATION_PREFIX = "CLARIFICATION NEEDED"

# Some unregistered keyword names are plot views that a registered module
# already emits (see its output_spec), so asking for them is satisfied by
# planning that module - do not report those as unavailable.
_PLOT_ALIASES: Dict[str, set] = {
    "volcano": {"microbiome_marker", "metabolome_marker", "maaslin3"},
    "heatmap": {"cross_correlation"},
}


def _filter_covered_aliases(unavailable: List[str], planned_modules: set) -> List[str]:
    """Drop 'unavailable' names whose output a planned module already produces."""
    return [
        name for name in unavailable
        if not (_PLOT_ALIASES.get(name, set()) & planned_modules)
    ]

_EXAMPLE_QUERIES = [
    "find differential markers comparing visits",
    "run PCoA and PERMANOVA on the microbiome",
    "correlate genera with metabolites",
    "alpha diversity by group",
]


def _clarification_plan(
    query: str,
    unavailable: Optional[List[str]] = None,
    reason: Optional[str] = None,
) -> ExecutionPlan:
    """Plan returned when the query cannot be mapped onto any analysis.

    Deliberately carries NO analysis steps: a validator-only plan dressed up as
    an analysis is worse than admitting the query was not understood.
    """
    notes = []
    if reason:
        notes.append(f"{CLARIFICATION_PREFIX}: {reason}")
    elif unavailable:
        notes.append(
            f"{CLARIFICATION_PREFIX}: the query asks for "
            f"{', '.join(sorted(unavailable))}, which is recognised but not "
            f"available in this deployment yet, and nothing else matched."
        )
    else:
        notes.append(
            f"{CLARIFICATION_PREFIX}: could not determine which analysis is "
            f"being requested, so no steps were planned."
        )
    notes.append("Please rephrase, e.g. " + "; ".join(f'"{q}"' for q in _EXAMPLE_QUERIES) + ".")
    notes.append(f"Available modules: {', '.join(sorted(get_module_names()))}")
    return ExecutionPlan(
        query=query,
        steps=[],
        estimated_time="~0 seconds",
        notes=notes,
        clarification_needed=True,
    )


def _keyword_steps(
    detected: List[Tuple[str, float]],
    data_types: Dict[str, bool],
    existing_modules: Optional[set] = None,
    start_index: int = 2,
    validator_id: str = "step1_validate",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Turn keyword hits into plan steps, skipping omics the query rules out.

    Returns ``(steps, skipped)``; ``skipped`` names modules that were dropped
    because the query explicitly scoped itself to one omics layer.
    """
    existing = set(existing_modules or ())
    steps: List[Dict[str, Any]] = []
    skipped: List[str] = []

    for module_name, _score in detected:
        if module_name in existing:
            continue
        spec = get_module_spec(module_name)
        if not spec:
            continue

        # Only skip on data the query explicitly rules out. When the query names
        # no omics layer at all, _infer_data_type reports both as available so
        # that ordinary phrasings still get a real plan.
        reqs = spec.input_requirements
        if reqs.get("microbiome") == "required" and not data_types["microbiome"]:
            skipped.append(module_name)
            continue
        if reqs.get("metabolome") == "required" and not data_types["metabolome"]:
            skipped.append(module_name)
            continue

        existing.add(module_name)
        steps.append({
            "module": module_name,
            "id": f"step{start_index + len(steps)}_{module_name}",
            "depends_on": [validator_id],
        })

    return steps, skipped


def _build_plan(
    query: str,
    template: Optional[Dict[str, Any]] = None,
    detected: Optional[List[Tuple[str, float]]] = None,
    unavailable: Optional[List[str]] = None,
) -> ExecutionPlan:
    """Build execution plan from template and/or keyword detection.

    Template and keyword routing are combined rather than mutually exclusive: a
    template match used to discard every other module the user asked for
    ("run PCoA and find markers" planned only markers).
    """
    notes: List[str] = []
    if detected is None or unavailable is None:
        detected, unavailable = _detect_modules_from_keywords(query)
    data_types = _infer_data_type(query)
    skipped_for_data: List[str] = []

    if template:
        # Deep-ish copy: _apply_best_practices writes into params/depends_on and
        # would otherwise mutate ANALYSIS_TEMPLATES for every later request.
        steps_raw = [
            dict(s, params=dict(s.get("params", {})), depends_on=list(s.get("depends_on", [])))
            for s in template["steps"]
        ]
        notes.append(f"Matched template: {template['name']}")
        notes.append(template["description"])
        notes.extend(template.get("notes", []))

        validator = next((s for s in steps_raw if s["module"] == "data_validator"), None)
        validator_id = validator["id"] if validator else "step1_validate"
        extra, skipped_for_data = _keyword_steps(
            detected,
            data_types,
            existing_modules={s["module"] for s in steps_raw},
            start_index=len(steps_raw) + 1,
            validator_id=validator_id,
        )
        if extra:
            steps_raw.extend(extra)
            notes.append(
                "Added from the query on top of the template: "
                + ", ".join(s["module"] for s in extra)
            )
    else:
        steps_raw = [{"module": "data_validator", "id": "step1_validate"}]
        extra, skipped_for_data = _keyword_steps(detected, data_types)
        steps_raw.extend(extra)
        notes.append(
            "Keyword-based planning detected: "
            + (", ".join(s["module"] for s in extra) if extra else "nothing")
        )

    # Drop steps whose module has no registered spec (templates still reference
    # modules that were never registered) and repair the dependency edges.
    steps_raw, dropped = _drop_unrunnable_steps(steps_raw)
    if dropped:
        notes.append(
            "Skipped (no executable module registered): " + ", ".join(sorted(dropped))
        )
    unavailable = _filter_covered_aliases(unavailable, {s["module"] for s in steps_raw})
    if unavailable:
        notes.append(
            "Requested but not available in this deployment: "
            + ", ".join(sorted(unavailable))
        )
    if skipped_for_data:
        notes.append(
            "Skipped (query scoped to "
            + ("microbiome" if data_types["microbiome"] else "metabolome")
            + " only): " + ", ".join(sorted(set(skipped_for_data)))
        )

    analysis_modules = [s for s in steps_raw if s["module"] != "data_validator"]
    if not analysis_modules and not (template and template.get("advisory")):
        return _clarification_plan(query, unavailable)

    # Apply best practices
    steps_raw = _apply_best_practices(steps_raw, query)

    # Resolve auto-dependencies for integration methods
    ordination_steps = {}
    for s in steps_raw:
        if s["module"] == "microbiome_pcoa":
            ordination_steps["microbiome"] = s["id"]
        elif s["module"] == "metabolome_pca":
            ordination_steps["metabolome"] = s["id"]

    for s in steps_raw:
        if s["module"] == "procrustes" and ordination_steps:
            s["depends_on"] = list(ordination_steps.values())

    # The report summarises everything, so it must run last no matter how it got
    # into the plan (template, keyword hit or best-practice injection).
    reports = [s for s in steps_raw if s["module"] == "report_generator"]
    others = [s for s in steps_raw if s["module"] != "report_generator"]
    if reports:
        upstream = [s["id"] for s in others if s["module"] != "data_validator"]
        for r in reports:
            r["depends_on"] = upstream or [s["id"] for s in others]
        steps_raw = others + reports

    if template and template.get("advisory"):
        notes.append(
            "Advisory request: no analysis steps were planned - the answer is a "
            "method recommendation, not a pipeline."
        )

    # Build PlanStep objects
    plan_steps = []
    for s in steps_raw:
        spec = get_module_spec(s["module"])
        desc = spec.description if spec else ""
        plan_steps.append(PlanStep(
            id=s["id"],
            module=s["module"],
            params=s.get("params", {}),
            depends_on=s.get("depends_on", []),
            description=desc,
        ))

    _prune_dangling_dependencies(plan_steps)

    return ExecutionPlan(
        query=query,
        steps=plan_steps,
        estimated_time=_estimate_time(len(plan_steps)),
        notes=notes,
    )


# ───────────────────────────────────────────────────────────────
# PUBLIC API
# ───────────────────────────────────────────────────────────────

class AnalysisPlanner:
    """Main planner class. Supports rule-based and LLM-based planning."""

    def __init__(self, use_llm: bool = False, openai_api_key: Optional[str] = None):
        self.use_llm = use_llm
        self.openai_api_key = openai_api_key

    async def plan(self, query: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        """
        Generate an execution plan from user query.

        Rule-based planning is the primary engine: it is deterministic,
        offline, and encodes the platform's analysis best practices. The LLM
        is a *fallback* -- consulted only when the rule engine cannot make
        sense of the query at all (``clarification_needed``). Any LLM plan is
        validated against the module registry before it is returned; if
        validation or the API call fails, the rule-based result stands.
        """
        logger.info(f"Planning analysis for query: {query[:100]}...")

        rule_plan = self._rule_plan(query, context)

        if self.use_llm and rule_plan.clarification_needed:
            llm_plan = await self._llm_plan(query, context)
            if llm_plan is not None:
                llm_plan.notes.append(
                    "Rule engine could not map this query; plan was generated "
                    "by the LLM planner and validated against the module registry."
                )
                return llm_plan
        return rule_plan

    def _data_aware_plan(self, query: str, context: Dict[str, Any]) -> Optional[ExecutionPlan]:
        """Recommend a pipeline from the uploaded files alone.

        Only used when the query itself carries no analysis intent - it ignores
        the query, so running it unconditionally (as before) meant any session
        query got the same generic pipeline back.
        """
        data_info = _infer_data_type_from_files(context["session_files"])
        if data_info["format"] == "unknown":
            return None

        steps = _get_recommended_steps(data_info)
        steps, dropped = _drop_unrunnable_steps(steps)
        steps = _apply_best_practices(steps, query)

        plan_steps = []
        for s in steps:
            spec = get_module_spec(s["module"])
            desc = spec.description if spec else ""
            plan_steps.append(PlanStep(
                id=s["id"],
                module=s["module"],
                params=s.get("params", {}),
                depends_on=s.get("depends_on", []),
                description=desc,
            ))
        _prune_dangling_dependencies(plan_steps)

        notes = [
            "No specific analysis was named - recommending a pipeline from the uploaded data.",
            f"Auto-detected data format: {data_info['format']}",
            f"Files: {', '.join(context['session_files'])}",
        ]
        if data_info["has_metaphlan"]:
            notes.append("MetaPhlAn shotgun data detected - using species-level profiling")
        if data_info["has_humann3"]:
            notes.append("HUMAnN3 functional data detected - adding pathway analysis")
        if dropped:
            notes.append("Skipped (no executable module registered): " + ", ".join(sorted(dropped)))

        return ExecutionPlan(
            query=query,
            steps=plan_steps,
            estimated_time=_estimate_time(len(plan_steps)),
            notes=notes,
        )

    def _rule_plan(self, query: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        """Rule-based planning (default, no API key needed)."""
        template = _match_template(query)
        detected, unavailable = _detect_modules_from_keywords(query)

        # Fall back to file-driven recommendations only when the query says
        # nothing specific ("analyze my data", or nothing we recognise).
        query_is_open_ended = (
            (template is None and not detected)
            or (template is not None and template["name"] == "auto_analyze")
        )
        if query_is_open_ended and context and context.get("session_files"):
            data_plan = self._data_aware_plan(query, context)
            if data_plan is not None:
                pending = _filter_covered_aliases(
                    unavailable, {s.module for s in data_plan.steps}
                )
                if pending:
                    data_plan.notes.append(
                        "Requested but not available in this deployment: "
                        + ", ".join(sorted(pending))
                    )
                logger.info("Data-aware plan generated: %d steps", len(data_plan.steps))
                return data_plan

        plan = _build_plan(query, template, detected, unavailable)

        # Drop steps whose data the session does not actually hold.
        available = _available_omics_from_context(context)
        if available == "microbiome_only":
            plan.steps = [s for s in plan.steps
                          if get_module_spec(s.module).input_requirements.get("metabolome") != "required"]
            plan.notes.append("Adjusted for microbiome-only data")
        elif available == "metabolome_only":
            plan.steps = [s for s in plan.steps
                          if get_module_spec(s.module).input_requirements.get("microbiome") != "required"]
            plan.notes.append("Adjusted for metabolome-only data")

        if available:
            _prune_dangling_dependencies(plan.steps)
            if not [s for s in plan.steps if s.module != "data_validator"]:
                # Everything the query asked for needs data this session lacks.
                return _clarification_plan(
                    query,
                    unavailable,
                    reason=(
                        f"every analysis this query asks for needs data the "
                        f"session does not have (it provides "
                        f"{available.replace('_only', '')} only), so no steps "
                        f"were planned."
                    ),
                )
            plan.estimated_time = _estimate_time(len(plan.steps))

        logger.info(f"Rule-based plan generated: {len(plan.steps)} steps")
        return plan

    async def _llm_plan(self, query: str, context: Optional[Dict[str, Any]] = None) -> Optional[ExecutionPlan]:
        """LLM-based planning via the Kimi gateway (app.services.llm_client).

        Returns None on any failure or registry-validation error so the
        caller can keep the rule-based result. Never raises.
        """
        from app.services.llm_client import get_llm_client

        client = get_llm_client()
        if not client.available:
            return None

        module_descriptions = []
        for name, spec in MODULE_REGISTRY.items():
            module_descriptions.append(
                f"- {name}: {spec.description} [category: {spec.category}]"
            )

        system_prompt = f"""You are a bioinformatics analysis planner for a microbiome/metabolome
platform. Given a user's request, output a JSON execution plan using ONLY these modules:

{chr(10).join(module_descriptions)}

Rules:
1. data_validator must be the first step, with id "step1_validate"
2. Every step: {{"id": "stepN_<module>", "module": "<one of the modules above>",
   "params": {{}}, "depends_on": ["<ids of prerequisite steps>"]}}
3. microbiome_marker MUST use transformation="clr" and test_method="mannwhitney"
4. metabolome_marker MUST use transformation="log1p" and test_method="welch"
5. Only use module names from the list above. No invented modules.
6. Output ONLY the JSON object: {{"steps": [...]}} - no markdown, no commentary.
"""
        try:
            content = client.chat(system_prompt, query, max_tokens=8000, timeout=120)
            if not content:
                return None
            text = content.strip()
            if text.startswith("```"):  # strip code fences if the model adds them
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            plan_json = json.loads(text)
            steps = self._validate_llm_steps(plan_json.get("steps") or [])
            if not steps:
                return None
            return ExecutionPlan(
                query=query,
                steps=steps,
                estimated_time=_estimate_time(len(steps)),
                notes=["Generated by LLM planner (kimi-for-coding)"],
            )
        except Exception as e:
            logger.warning(f"LLM planning failed: {e}; keeping rule-based result")
            return None

    @staticmethod
    def _validate_llm_steps(raw_steps: List[Dict[str, Any]]) -> List[PlanStep]:
        """Keep only steps whose module exists in the registry; fix order so
        data_validator comes first; drop dangling dependencies."""
        steps: List[PlanStep] = []
        seen_ids = set()
        for i, s in enumerate(raw_steps, 1):
            module = str(s.get("module") or "")
            if module not in MODULE_REGISTRY:
                logger.warning(f"LLM proposed unknown module '{module}' - dropped")
                continue
            step_id = str(s.get("id") or f"step{i}_{module}")
            while step_id in seen_ids:
                step_id += "_x"
            seen_ids.add(step_id)
            spec = get_module_spec(module)
            steps.append(PlanStep(
                id=step_id,
                module=module,
                params=s.get("params") or {},
                depends_on=[d for d in (s.get("depends_on") or []) if isinstance(d, str)],
                description=spec.description if spec else "",
            ))
        # data_validator must lead
        steps.sort(key=lambda s: 0 if s.module == "data_validator" else 1)
        _prune_dangling_dependencies(steps)
        # A validator-only plan is not a plan.
        if not [s for s in steps if s.module != "data_validator"]:
            return []
        return steps


# Singleton instance
_default_planner: Optional[AnalysisPlanner] = None


def get_planner(use_llm: bool = False, api_key: Optional[str] = None) -> AnalysisPlanner:
    """Get or create the default planner instance.

    The singleton used to freeze ``use_llm`` from whichever request created
    it first, so a later ``use_llm=true`` request silently got a rule-only
    planner (and vice versa). The flag now follows each call.
    """
    global _default_planner
    if _default_planner is None:
        _default_planner = AnalysisPlanner(use_llm=use_llm, openai_api_key=api_key)
    else:
        _default_planner.use_llm = use_llm
        if api_key:
            _default_planner.openai_api_key = api_key
    return _default_planner
