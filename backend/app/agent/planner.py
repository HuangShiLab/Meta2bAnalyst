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
    """Complete execution plan as a DAG."""
    query: str
    steps: List[PlanStep]
    estimated_time: str = ""
    notes: List[str] = field(default_factory=list)


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
            r"标记物|差异.*分析|差异.*代谢物|差异.*菌",
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
            r"交叉.*相关|菌属.*代谢物.*相关|热图.*相关",
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
    "microbiome_marker": ["microbiome.*marker", "microbiome.*differential", "clr.*wilcoxon", "微生物组.*标记", "微生物组.*差异", "differential.*abundance", "biomarker", "biomarker.*discovery", "marker.*discovery", "significant.*taxa", "significant.*feature"],
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
    "sparse_cca": ["sparse.*cca", "scca", "canonical", "典型.*相关"],
    "rda": ["rda", "redundancy", "冗余.*分析"],
    "o2pls": ["o2pls", "joint.*variation", "orthogonal"],
    "cross_correlation": ["cross.*correlation", "heatmap", "genus.*metabolite", "菌属.*代谢物"],
    "moafa": ["mofa", "mofa\+", "factor.*analysis", "multi-omics.*factor"],
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
    """Match query against predefined templates using regex patterns."""
    query_lower = query.lower()
    for template in ANALYSIS_TEMPLATES:
        for pattern in template["patterns"]:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return template
    return None


def _detect_modules_from_keywords(query: str) -> List[Tuple[str, float]]:
    """Detect individual modules mentioned in query with confidence scores."""
    query_lower = query.lower()
    matched = []
    for module_name, keywords in MODULE_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if re.search(kw, query_lower, re.IGNORECASE):
                score += 1
        if score > 0:
            matched.append((module_name, score))
    # Sort by confidence
    matched.sort(key=lambda x: x[1], reverse=True)
    return matched


def _infer_data_type(query: str) -> Dict[str, bool]:
    """Infer which omics data types are mentioned."""
    q = query.lower()
    has_mb = any(k in q for k in ["microbiome", "microbial", "16s", "bacteria", "taxa", "genus", "微生物组", "菌群", "细菌"])
    has_met = any(k in q for k in ["metabolome", "metabolite", "metabolic", "lc-ms", "代谢组", "代谢物"])
    # Default to both if neither is explicitly mentioned but multi-omics context
    if not has_mb and not has_met:
        if any(k in q for k in ["multi.?omics", "multiomics", "整合", "integration", "联合", "correlation"]):
            has_mb = True
            has_met = True
    return {"microbiome": has_mb, "metabolome": has_met}


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


def _build_plan(query: str, template: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
    """Build execution plan from template or keyword detection."""
    notes = []

    if template:
        steps_raw = template["steps"]
        notes.append(f"Matched template: {template['name']}")
        notes.append(template["description"])
    else:
        # Fall back to keyword-based module detection
        detected = _detect_modules_from_keywords(query)
        data_types = _infer_data_type(query)

        steps_raw = [{"module": "data_validator", "id": "step1_validate"}]

        for module_name, score in detected:
            spec = get_module_spec(module_name)
            if not spec:
                continue

            # Skip modules that need data we don't have
            reqs = spec.input_requirements
            if reqs.get("microbiome") == "required" and not data_types["microbiome"]:
                continue
            if reqs.get("metabolome") == "required" and not data_types["metabolome"]:
                continue

            step_id = f"step{len(steps_raw)+1}_{module_name}"
            depends_on = ["step1_validate"]

            # Add dependencies on ordination steps for integration methods
            if module_name == "procrustes":
                depends_on = ["step1_validate"]  # Will be resolved later

            steps_raw.append({
                "module": module_name,
                "id": step_id,
                "depends_on": depends_on,
            })

        notes.append(f"Keyword-based planning detected: {[m for m, _ in detected[:5]]}")

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

    # Build PlanStep objects
    plan_steps = []
    for i, s in enumerate(steps_raw):
        spec = get_module_spec(s["module"])
        desc = spec.description if spec else ""
        plan_steps.append(PlanStep(
            id=s["id"],
            module=s["module"],
            params=s.get("params", {}),
            depends_on=s.get("depends_on", []),
            description=desc,
        ))

    # Estimate time
    n_steps = len(plan_steps)
    est_time = f"~{n_steps * 15}-{(n_steps * 15) + 30} seconds"
    if n_steps > 8:
        est_time = f"~{(n_steps * 15) // 60}-{(n_steps * 15 + 60) // 60} minutes"

    return ExecutionPlan(
        query=query,
        steps=plan_steps,
        estimated_time=est_time,
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

        Args:
            query: Natural language description of the desired analysis
            context: Optional context (e.g., available data types, previous analyses)

        Returns:
            ExecutionPlan: Structured DAG of analysis steps
        """
        logger.info(f"Planning analysis for query: {query[:100]}...")

        if self.use_llm and self.openai_api_key:
            return await self._llm_plan(query, context)
        else:
            return self._rule_plan(query, context)

    def _rule_plan(self, query: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        """Rule-based planning (default, no API key needed)."""
        
        # Check for data-aware auto-analysis
        if context and context.get("session_files"):
            data_info = _infer_data_type_from_files(context["session_files"])
            if data_info["format"] != "unknown":
                # User asked for auto-analysis with uploaded files
                steps = _get_recommended_steps(data_info)
                steps = _apply_best_practices(steps, query)
                
                plan_steps = []
                for i, s in enumerate(steps):
                    spec = get_module_spec(s["module"])
                    desc = spec.description if spec else ""
                    plan_steps.append(PlanStep(
                        id=s["id"],
                        module=s["module"],
                        params=s.get("params", {}),
                        depends_on=s.get("depends_on", []),
                        description=desc,
                    ))
                
                notes = [
                    f"Auto-detected data format: {data_info['format']}",
                    f"Files: {', '.join(context['session_files'])}",
                ]
                if data_info["has_metaphlan"]:
                    notes.append("MetaPhlAn shotgun data detected - using species-level profiling")
                if data_info["has_humann3"]:
                    notes.append("HUMAnN3 functional data detected - adding pathway analysis")
                
                return ExecutionPlan(
                    query=query,
                    steps=plan_steps,
                    estimated_time=f"~{len(plan_steps) * 15}-{len(plan_steps) * 15 + 30} seconds",
                    notes=notes,
                )
        
        # Try template matching first
        template = _match_template(query)
        plan = _build_plan(query, template)

        # Add context-based adjustments
        if context:
            if context.get("available_data") == "microbiome_only":
                # Remove metabolome-dependent steps
                plan.steps = [s for s in plan.steps
                              if get_module_spec(s.module).input_requirements.get("metabolome") != "required"]
                plan.notes.append("Adjusted for microbiome-only data")
            elif context.get("available_data") == "metabolome_only":
                plan.steps = [s for s in plan.steps
                              if get_module_spec(s.module).input_requirements.get("microbiome") != "required"]
                plan.notes.append("Adjusted for metabolome-only data")

        logger.info(f"Rule-based plan generated: {len(plan.steps)} steps")
        return plan

    async def _llm_plan(self, query: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        """LLM-based planning (requires OpenAI API key)."""
        try:
            import openai
            openai.api_key = self.openai_api_key

            # Build module descriptions for the prompt
            module_descriptions = []
            for name, spec in MODULE_REGISTRY.items():
                module_descriptions.append(
                    f"- {name}: {spec.description} [category: {spec.category}]"
                )

            system_prompt = f"""You are a bioinformatics analysis planner. Given a user's request, 
output a JSON execution plan using ONLY these available modules:

{chr(10).join(module_descriptions)}

Rules:
1. microbiome_marker MUST use transformation="clr" and test_method="mannwhitney"
2. metabolome_marker MUST use transformation="log1p" and test_method="welch"
3. data_validator must be the first step
4. Procrustes requires microbiome_pcoa and metabolome_pca to complete first
5. Output valid JSON with "steps" array, each with "module", "params", "depends_on", "id"
"""

            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                temperature=0.2,
            )

            plan_json = json.loads(response.choices[0].message.content)
            steps = [PlanStep(**s) for s in plan_json["steps"]]

            return ExecutionPlan(
                query=query,
                steps=steps,
                estimated_time="~LLM-generated",
                notes=["Generated by LLM planner"],
            )

        except Exception as e:
            logger.warning(f"LLM planning failed: {e}, falling back to rule-based")
            return self._rule_plan(query, context)


# Singleton instance
_default_planner: Optional[AnalysisPlanner] = None


def get_planner(use_llm: bool = False, api_key: Optional[str] = None) -> AnalysisPlanner:
    """Get or create the default planner instance."""
    global _default_planner
    if _default_planner is None:
        _default_planner = AnalysisPlanner(use_llm=use_llm, openai_api_key=api_key)
    return _default_planner
