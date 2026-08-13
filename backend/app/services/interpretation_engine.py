"""
Enhanced Interpretation Engine
==============================
Cross-analysis integration + knowledge-driven interpretation + optional LLM enhancement.

Takes ALL analysis results from a session and produces:
1. Integrated narrative (cross-analysis story)
2. Biological context (per-taxon annotations from KB)
3. Caveats (data quality + method assumptions)
4. Follow-up suggestions (from method KB)
5. Contradiction detection
6. Disease relevance mapping

Optional: LLM (Kimi API) rewrites narrative for clarity and depth
          while preserving all KB-derived facts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.knowledge import (
    fuzzy_lookup_taxon,
    lookup_disease,
    lookup_method,
)
from app.services.llm_client import get_llm_client

logger = logging.getLogger(__name__)


@dataclass
class IntegratedInterpretation:
    integrated_narrative: str = ""
    biological_context: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    follow_up_suggestions: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    disease_relevance: List[Dict[str, Any]] = field(default_factory=list)
    llm_enhanced: bool = False
    llm_model: Optional[str] = None


class EnhancedInterpreter:
    """
    Knowledge-enhanced interpreter that integrates results across analyses
    and annotates findings with structured domain knowledge.
    Optional LLM layer for narrative refinement.
    """

    def __init__(self):
        pass

    # ═══════════════════════════════════════════════════════════════
    # Main entry point
    # ═══════════════════════════════════════════════════════════════

    def interpret_full(
        self,
        all_results: Dict[str, Dict[str, Any]],
        metadata_summary: Optional[Dict[str, Any]] = None,
        question: Optional[str] = None,
    ) -> IntegratedInterpretation:
        """
        Produce a fully integrated interpretation from all session results.

        Parameters
        ----------
        all_results : dict
            Keys are analysis names. Values are API response dicts.
        metadata_summary : dict, optional
            Session-level metadata.
        question : str, optional
            User's specific question (passed to LLM for targeted rewriting).

        Returns
        -------
        IntegratedInterpretation
        """
        interp = IntegratedInterpretation()

        # 1. Cross-analysis integration (most important)
        interp.integrated_narrative = self._build_integrated_narrative(all_results)
        interp.contradictions = self._detect_contradictions(all_results)

        # 2. Biological context for significant taxa
        interp.biological_context = self._annotate_taxa(all_results)

        # 3. Disease relevance mapping
        interp.disease_relevance = self._assess_disease_relevance(all_results)

        # 4. Data quality & method caveats
        interp.caveats = self._generate_caveats(all_results, metadata_summary)

        # 5. Follow-up suggestions from method KB
        interp.follow_up_suggestions = self._suggest_follow_up(all_results)

        # 6. Optional LLM enhancement
        llm = get_llm_client()
        if llm.available:
            enhanced = llm.enhance_narrative(
                integrated_narrative=interp.integrated_narrative,
                biological_context=interp.biological_context,
                caveats=interp.caveats,
                follow_up=interp.follow_up_suggestions,
                contradictions=interp.contradictions,
                disease_relevance=interp.disease_relevance,
                question=question,
            )
            if enhanced.get("llm_used"):
                interp.integrated_narrative = enhanced["enhanced_narrative"]
                interp.llm_enhanced = True
                interp.llm_model = enhanced.get("model")
                logger.info(f"LLM enhancement applied using {enhanced.get('model')}")

        return interp

    # ═══════════════════════════════════════════════════════════════
    # 1. Cross-analysis narrative
    # ═══════════════════════════════════════════════════════════════

    def _build_integrated_narrative(self, results: Dict[str, Any]) -> str:
        """Build a coherent story from all analyses."""
        paragraphs = []

        # Extract key stats safely
        alpha = self._get_nested(results, "alpha-diversity", "result_data")
        beta = self._get_nested(results, "permanova", "result_data") or \
               self._get_nested(results, "anosim", "result_data")
        diff = self._get_nested(results, "differential", "result_data") or \
               self._get_nested(results, "lefse", "result_data") or \
               self._get_nested(results, "ancom", "result_data")

        # Overall summary
        n_analyses = len([k for k in results if results[k].get("status") == "completed"])
        paragraphs.append(
            f"A comprehensive microbiome analysis was performed using {n_analyses} analytical modules. "
        )

        # Alpha diversity story
        if alpha:
            shannon_stats = self._get_nested(alpha, "group_statistics", "shannon", "statistical_test")
            if shannon_stats:
                p = shannon_stats.get("pvalue")
                sig = shannon_stats.get("significant", False)
                if sig:
                    paragraphs.append(
                        f"Alpha diversity analysis revealed a statistically significant difference "
                        f"in Shannon diversity between groups ({self._fmt_p(p)}). "
                        f"This indicates that the overall species richness and evenness within samples "
                        f"differs between the compared groups. "
                    )
                else:
                    paragraphs.append(
                        f"Alpha diversity (Shannon index) did not differ significantly between groups "
                        f"({self._fmt_p(p)}). This suggests that the overall within-sample ecological "
                        f"complexity is comparable across conditions. "
                    )

        # Beta diversity story
        if beta:
            p = beta.get("pvalue")
            r2 = beta.get("r2")
            sig = beta.get("significant", False)
            r2_str = f"{r2:.3f}" if r2 is not None else "not reported"
            if sig:
                paragraphs.append(
                    f"PERMANOVA on Bray-Curtis distances demonstrated a significant separation "
                    f"in community composition between groups ({self._fmt_p(p)}, R\u00b2 = {r2_str}). "
                    f"The microbiome structure is therefore distinct across the compared conditions. "
                )
            else:
                paragraphs.append(
                    f"PERMANOVA found no significant difference in overall community composition "
                    f"({self._fmt_p(p)}, R\u00b2 = {r2_str}). The microbial community structure appears "
                    f"broadly similar between groups. "
                )
        # Differential abundance story
        if diff:
            n_sig = diff.get("n_significant", 0)
            top = diff.get("top_feature") or diff.get("top_taxa", [None])[0]
            if n_sig > 0 and top:
                paragraphs.append(
                    f"Differential abundance testing identified {n_sig} significantly altered feature(s). "
                    f"Notably, {self._shorten_name(top)} showed differential abundance, suggesting "
                    f"targeted taxonomic restructuring rather than global community turnover. "
                )

        # Cross-analysis integration (the key insight)
        alpha_sig = self._is_significant(results, "alpha-diversity")
        beta_sig = self._is_significant(results, "permanova")
        diff_sig = self._has_differential(results)

        if not alpha_sig and not beta_sig and diff_sig:
            paragraphs.append(
                "**Integrated insight**: Although overall diversity (alpha) and community structure "
                "(beta) did not change significantly, specific taxa were differentially abundant. "
                "This pattern—'taxonomic substitution without ecological disruption'—is consistent with "
                "functional redundancy, where different species perform similar roles, maintaining "
                "overall community function despite species turnover."
            )
        elif alpha_sig and beta_sig and diff_sig:
            paragraphs.append(
                "**Integrated insight**: Significant changes were observed at all three levels "
                "(alpha, beta, and differential abundance), indicating a robust and coherent "
                "microbiome shift. The community has undergone both structural and compositional "
                "restructuring."
            )
        elif not alpha_sig and beta_sig and not diff_sig:
            paragraphs.append(
                "**Integrated insight**: Community composition differed (beta) but no specific "
                "taxa were identified as differentially abundant. This may indicate a broad, "
                "subtle shift across many low-abundance taxa rather than a few dominant drivers."
            )

        return "\n\n".join(paragraphs)

    # ═══════════════════════════════════════════════════════════════
    # 2. Contradiction detection
    # ═══════════════════════════════════════════════════════════════

    def _detect_contradictions(self, results: Dict[str, Any]) -> List[str]:
        """Detect statistical contradictions across analyses."""
        contradictions = []

        alpha_sig = self._is_significant(results, "alpha-diversity")
        beta_sig = self._is_significant(results, "permanova")
        diff_sig = self._has_differential(results)

        if alpha_sig and not beta_sig:
            contradictions.append(
                "Alpha diversity is significant but beta diversity is not. "
                "This is unusual: within-sample diversity changes should usually accompany "
                "between-sample compositional shifts. Check for outliers or batch effects."
            )

        if beta_sig and not diff_sig:
            contradictions.append(
                "Beta diversity (PERMANOVA) is significant but no differential taxa were found. "
                "This can occur when the effect is distributed across many low-abundance taxa, "
                "or when dispersion differs between groups (check PERMDISP)."
            )

        if not alpha_sig and not beta_sig and diff_sig:
            contradictions.append(
                "Differential abundance was detected despite non-significant alpha and beta diversity. "
                "This is biologically plausible (taxonomic substitution with functional redundancy), "
                "but verify that the differential method assumptions are met."
            )

        # Method assumption checks
        for aname in ["differential", "lefse", "ancom", "deseq2", "aldex2"]:
            r = results.get(aname, {}).get("result_data", {})
            if r and r.get("sparsity", 0) > 0.9:
                contradictions.append(
                    f"{aname} results may be unreliable: data sparsity is {r['sparsity']:.1%}, "
                    f"exceeding the recommended threshold. Consider genus-level aggregation or imputation."
                )

        return contradictions

    # ═══════════════════════════════════════════════════════════════
    # 3. Taxon annotation
    # ═══════════════════════════════════════════════════════════════

    def _annotate_taxa(self, results: Dict[str, Any]) -> List[str]:
        """Look up biological context for significant taxa from KB."""
        annotations = []
        significant_taxa = self._extract_significant_taxa(results)

        for taxon in significant_taxa:
            # Try exact match, then fuzzy
            info = fuzzy_lookup_taxon(taxon, limit=1)
            if not info:
                continue
            info = info[0]

            products = ", ".join(info.get("main_products", [])[:3])
            functions = ", ".join(info.get("known_functions", [])[:3])

            # Disease associations
            diseases = []
            if "disease_associations" in info:
                for d, assoc in info["disease_associations"].items():
                    diseases.append(f"{d} ({assoc})")
            disease_str = "; ".join(diseases[:3])

            annotation = (
                f"**{self._shorten_name(taxon)}**: {info.get('oxygen', 'unknown oxygen requirement')} "
                f"{info.get('gram_stain', '')}. Key products: {products}. "
                f"Known for: {functions}."
            )
            if disease_str:
                annotation += f" Disease associations: {disease_str}."
            if info.get("notes"):
                annotation += f" {info['notes']}"

            annotations.append(annotation)

        return annotations

    # ═══════════════════════════════════════════════════════════════
    # 4. Disease relevance
    # ═══════════════════════════════════════════════════════════════

    def _assess_disease_relevance(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Map significant taxa to known disease signatures."""
        relevances = []
        significant_taxa = set(self._extract_significant_taxa(results))

        # Dynamically load all diseases from KB instead of hard-coded list
        from app.knowledge.loader import get_all_diseases
        diseases = get_all_diseases()

        for disease_name in diseases:
            dinfo = lookup_disease(disease_name)
            if not dinfo:
                continue

            key_genera = dinfo.get("key_genera", [])
            matched = []
            for genus in key_genera:
                for taxon in significant_taxa:
                    if genus.lower() in taxon.lower():
                        matched.append(taxon)

            if matched:
                relevances.append({
                    "disease": disease_name,
                    "matched_taxa": matched,
                    "description": dinfo.get("description", ""),
                    "indicators": dinfo.get("indicators", []),
                })

        return relevances

    # ═══════════════════════════════════════════════════════════════
    # 5. Caveats
    # ═══════════════════════════════════════════════════════════════

    def _generate_caveats(
        self,
        results: Dict[str, Any],
        metadata_summary: Optional[Dict[str, Any]],
    ) -> List[str]:
        """Generate data quality and method assumption caveats."""
        caveats = []

        # Sample size
        n_samples = metadata_summary.get("n_samples", 0) if metadata_summary else 0
        if n_samples > 0 and n_samples < 20:
            caveats.append(
                f"Sample size is small (n={n_samples}). Statistical power is limited; "
                f"negative results may be false negatives."
            )

        # Check each completed analysis for method-specific caveats
        analysis_type_map = {
            "alpha-diversity": "alpha_diversity",
            "permanova": "permanova",
            "lefse": "lefse",
            "ancom": "ancom",
            "deseq2": "deseq2",
            "aldex2": "aldex2",
            "maaslin2": "maaslin2",
            "pcoa": "pcoa",
            "rarefaction": "rarefaction",
        }

        for api_name, kb_name in analysis_type_map.items():
            if api_name not in results:
                continue
            method_info = lookup_method(kb_name)
            if not method_info:
                continue
            for caution in method_info.get("cautions", [])[:2]:
                caveats.append(f"[{api_name}] {caution}")

        # Data-specific caveats
        alpha = self._get_nested(results, "alpha-diversity", "result_data")
        if alpha:
            for metric in ["shannon", "simpson"]:
                gs = self._get_nested(alpha, "group_statistics", metric, "statistical_test")
                if gs:
                    p = gs.get("pvalue")
                    if p is not None and 0.05 <= p < 0.1:
                        caveats.append(
                            f"Alpha diversity ({metric}) is borderline significant "
                            f"(p = {p:.3f}); a larger sample may clarify the effect."
                        )

        beta = self._get_nested(results, "permanova", "result_data")
        if beta:
            r2 = beta.get("r2")
            if r2 is not None and r2 < 0.05:
                caveats.append(
                    f"PERMANOVA R\u00b2 is small ({r2:.3f}). Although statistically significant, "
                    f"the biological relevance of the compositional difference may be limited."
                )

        return caveats

    # ═══════════════════════════════════════════════════════════════
    # 6. Follow-up suggestions
    # ═══════════════════════════════════════════════════════════════

    def _suggest_follow_up(self, results: Dict[str, Any]) -> List[str]:
        """Suggest next analyses based on completed results."""
        suggestions = []

        # If PERMANOVA significant → differential abundance
        if self._is_significant(results, "permanova"):
            suggestions.append(
                "PERMANOVA detected compositional differences. Run differential abundance "
                "analysis (LEfSe, ANCOM, or ALDEx2) to identify specific taxa driving the separation."
            )

        # If alpha significant but beta not → check dispersion
        if self._is_significant(results, "alpha-diversity") and not self._is_significant(results, "permanova"):
            suggestions.append(
                "Alpha diversity changed but beta diversity did not. Consider checking "
                "PERMDISP to verify homogeneity of multivariate dispersion."
            )

        # If no significant results anywhere → power/sample size
        has_any_sig = any([
            self._is_significant(results, "alpha-diversity"),
            self._is_significant(results, "permanova"),
            self._has_differential(results),
        ])
        if not has_any_sig:
            suggestions.append(
                "No significant differences detected across analyses. Consider: "
                "(1) increasing sample size, (2) reducing taxonomic granularity to genus level, "
                "(3) stratifying by confounders (diet, medication, age), or "
                "(4) moving to functional profiling if taxonomic differences are absent."
            )

        # If differential found → functional validation
        if self._has_differential(results):
            suggestions.append(
                "Differential taxa identified. Consider functional prediction "
                "(PICRUSt2 or HUMAnN3) to assess whether taxonomic shifts translate "
                "to functional consequences."
            )

        # General suggestions
        suggestions.append(
            "Validate key findings in an independent cohort or with orthogonal methods "
            "(e.g., qPCR for top hits)."
        )

        return suggestions

    # ═══════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _get_nested(d: Dict, *keys: str) -> Optional[Any]:
        """Safely traverse nested dicts."""
        for k in keys:
            if not isinstance(d, dict):
                return None
            d = d.get(k)
            if d is None:
                return None
        return d

    @staticmethod
    def _fmt_p(p: Optional[float]) -> str:
        if p is None:
            return "p not reported"
        if p < 0.001:
            return "p < 0.001"
        return f"p = {p:.3f}"

    def _is_significant(self, results: Dict, analysis_name: str) -> bool:
        """Check if an analysis result is statistically significant."""
        r = results.get(analysis_name, {}).get("result_data", {})
        if not r:
            return False
        # Try various significance indicators
        if "pvalue" in r:
            return r.get("pvalue", 1.0) < 0.05
        if "statistical_test" in r:
            st = r["statistical_test"]
            if isinstance(st, dict):
                return st.get("significant", False)
        # For alpha diversity nested structure
        for metric in ["shannon", "simpson", "observed"]:
            gs = self._get_nested(r, "group_statistics", metric, "statistical_test")
            if gs and gs.get("significant"):
                return True
        return False

    def _has_differential(self, results: Dict) -> bool:
        """Check if any differential analysis found significant features."""
        for aname in ["differential", "lefse", "ancom", "deseq2", "aldex2", "maaslin2"]:
            r = results.get(aname, {}).get("result_data", {})
            if r and r.get("n_significant", 0) > 0:
                return True
            # Some results use top_features or similar
            if r and (r.get("top_feature") or r.get("top_taxa")):
                return True
        return False

    def _extract_significant_taxa(self, results: Dict) -> List[str]:
        """Extract all significant taxa names from differential results."""
        taxa = []
        for aname in ["differential", "lefse", "ancom", "deseq2", "aldex2", "maaslin2"]:
            r = results.get(aname, {}).get("result_data", {})
            if not r:
                continue
            # Check top_feature / top_taxa
            top = r.get("top_feature") or r.get("top_taxa")
            if isinstance(top, str):
                taxa.append(top)
            elif isinstance(top, list):
                taxa.extend(top)
            # Check significant_features (LEfSe style: list of dicts with 'feature' key)
            sig_features = r.get("significant_features")
            if isinstance(sig_features, list):
                for feat in sig_features:
                    if isinstance(feat, dict):
                        fname = feat.get("feature")
                        if fname:
                            taxa.append(fname)
                    elif isinstance(feat, str):
                        taxa.append(feat)
        # Also check taxonomy-bar top taxa
        tb = self._get_nested(results, "taxonomy-bar", "result_data", "statistics", "top_taxa")
        if isinstance(tb, list):
            taxa.extend(tb)
        # Deduplicate while preserving order
        seen = set()
        return [t for t in taxa if not (t in seen or seen.add(t))]

    @staticmethod
    def _shorten_name(taxon: str) -> str:
        """Shorten MetaPhlAn-style taxon name for readability."""
        if "|" in taxon:
            return taxon.split("|")[-1].replace("s__", "").replace("g__", "")
        return taxon.replace("s__", "").replace("g__", "")
