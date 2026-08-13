"""
Agent Result Integrator
=======================
Combines results from multiple analysis steps into a unified report.

Supports:
- PDF report generation with figures and tables
- HTML report with interactive Plotly charts
- Markdown summary for documentation
- Structured JSON for API consumption
"""
import logging
from collections import defaultdict
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ReportSection:
    """A section in the integrated report."""
    title: str
    content: str = ""
    plot_data: Optional[Dict[str, Any]] = None
    table_data: Optional[List[Dict[str, Any]]] = None
    statistics: Optional[Dict[str, Any]] = None
    order: int = 0


class ResultIntegrator:
    """Integrates analysis results into structured reports."""

    # Section ordering for standard multi-omics reports
    SECTION_ORDER = {
        "data_summary": 0,
        "microbiome_pcoa": 10,
        "metabolome_pca": 20,
        "permanova": 30,
        "microbiome_alpha": 35,
        "metabolome_alpha": 36,
        "microbiome_marker": 40,
        "metabolome_marker": 50,
        "procrustes": 60,
        "mantel_test": 70,
        "sparse_cca": 80,
        "rda": 90,
        "o2pls": 100,
        "cross_correlation": 110,
        "network_sparcc": 120,
        "pathway_kegg": 130,
        "functional_prediction": 140,
        "conclusions": 999,
    }

    def __init__(self):
        self.sections: List[ReportSection] = []

    def integrate(self, state: Dict[str, Any], plan: Any = None) -> Dict[str, Any]:
        """
        Integrate all results into a structured report.

        Args:
            state: Mapping of step_id -> analysis result
            plan: Optional ExecutionPlan for context

        Returns:
            Dict with report sections, summary, and metadata
        """
        self.sections = []

        # Extract results by module type
        module_results = self._categorize_results(state)

        # Build sections
        self._add_data_summary(module_results)
        self._add_individual_omics(module_results)
        self._add_statistical_tests(module_results)
        self._add_markers(module_results)
        self._add_integration(module_results)
        self._add_feature_level(module_results)
        self._add_conclusions(module_results)

        # Sort by order
        self.sections.sort(key=lambda s: s.order)

        return {
            "title": "Multi-omics Analysis Report",
            "generated_at": __import__('time').time(),
            "n_sections": len(self.sections),
            "sections": [
                {
                    "title": s.title,
                    "content": s.content,
                    "has_plot": s.plot_data is not None,
                    "has_table": s.table_data is not None,
                    "statistics": s.statistics,
                }
                for s in self.sections
            ],
            "summary": self._generate_summary(module_results),
        }

    def _categorize_results(self, state: Dict[str, Any]) -> Dict[str, List[Any]]:
        """Categorize results by module type."""
        categorized = defaultdict(list)
        for step_id, result in state.items():
            # Extract module name from step_id (e.g., "step2_mb_pcoa" -> "microbiome_pcoa")
            module_name = self._extract_module_name(step_id)
            categorized[module_name].append(result)
        return dict(categorized)

    def _extract_module_name(self, step_id: str) -> str:
        """Extract module name from step_id."""
        # step IDs are like "step2_mb_pcoa" or "step1_validate"
        parts = step_id.split("_")
        if len(parts) >= 2:
            # Try to match against known modules
            for i in range(len(parts) - 1, 0, -1):
                candidate = "_".join(parts[i:])
                if candidate in self.SECTION_ORDER:
                    return candidate
            # Fallback: last part
            return parts[-1]
        return step_id

    def _add_data_summary(self, results: Dict[str, List[Any]]):
        """Add data validation / summary section."""
        if "data_validator" in results:
            self.sections.append(ReportSection(
                title="Data Summary",
                content="Input data validation and summary statistics.",
                order=self.SECTION_ORDER["data_summary"],
            ))

    def _add_individual_omics(self, results: Dict[str, List[Any]]):
        """Add individual omics profiling sections."""
        if "microbiome_pcoa" in results:
            r = results["microbiome_pcoa"][0]
            self.sections.append(ReportSection(
                title="Microbiome PCoA",
                content="Principal Coordinate Analysis of microbiome composition.",
                plot_data=r.get("plot_data") if isinstance(r, dict) else None,
                statistics=r.get("statistics") if isinstance(r, dict) else None,
                order=self.SECTION_ORDER["microbiome_pcoa"],
            ))

        if "metabolome_pca" in results:
            r = results["metabolome_pca"][0]
            self.sections.append(ReportSection(
                title="Metabolome PCA",
                content="Principal Component Analysis of metabolite intensities.",
                plot_data=r.get("plot_data") if isinstance(r, dict) else None,
                statistics=r.get("statistics") if isinstance(r, dict) else None,
                order=self.SECTION_ORDER["metabolome_pca"],
            ))

    def _add_statistical_tests(self, results: Dict[str, List[Any]]):
        """Add PERMANOVA and alpha diversity sections."""
        permanova_results = []
        for key in results:
            if "permanova" in key:
                permanova_results.extend(results[key])

        if permanova_results:
            stats_list = []
            for r in permanova_results:
                if isinstance(r, dict) and "statistics" in r:
                    stats_list.append(r["statistics"])

            self.sections.append(ReportSection(
                title="PERMANOVA: Metadata Effects",
                content="Permutational multivariate analysis of variance for metadata effects on each omics layer.",
                statistics={"permanova_results": stats_list},
                order=self.SECTION_ORDER["permanova"],
            ))

        # Alpha diversity
        for module, title in [("microbiome_alpha", "Microbiome Alpha Diversity"),
                              ("metabolome_alpha", "Metabolome Alpha Diversity")]:
            if module in results:
                r = results[module][0]
                self.sections.append(ReportSection(
                    title=title,
                    content=f"{title} analysis across groups.",
                    plot_data=r.get("plot_data") if isinstance(r, dict) else None,
                    order=self.SECTION_ORDER.get(module, 35),
                ))

    def _add_markers(self, results: Dict[str, List[Any]]):
        """Add marker discovery sections."""
        if "microbiome_marker" in results:
            r = results["microbiome_marker"][0]
            sig_count = 0
            if isinstance(r, dict):
                sig = r.get("significant_features", [])
                sig_count = len(sig) if isinstance(sig, list) else 0

            self.sections.append(ReportSection(
                title="Microbiome Marker Discovery (CLR + Wilcoxon)",
                content=f"Differential abundance analysis using CLR transformation and Wilcoxon rank-sum test. "
                        f"Found {sig_count} significant features.",
                plot_data=r.get("volcano_plot") or (r.get("plot_data") if isinstance(r, dict) else None),
                table_data=r.get("significant_features") if isinstance(r, dict) else None,
                statistics=r.get("statistics") if isinstance(r, dict) else None,
                order=self.SECTION_ORDER["microbiome_marker"],
            ))

        if "metabolome_marker" in results:
            r = results["metabolome_marker"][0]
            sig_count = 0
            if isinstance(r, dict):
                sig = r.get("significant_features", [])
                sig_count = len(sig) if isinstance(sig, list) else 0

            self.sections.append(ReportSection(
                title="Metabolome Marker Discovery (log1p + Welch t-test)",
                content=f"Differential metabolite analysis using log1p transformation and Welch t-test. "
                        f"Found {sig_count} significant features.",
                plot_data=r.get("volcano_plot") or (r.get("plot_data") if isinstance(r, dict) else None),
                table_data=r.get("significant_features") if isinstance(r, dict) else None,
                statistics=r.get("statistics") if isinstance(r, dict) else None,
                order=self.SECTION_ORDER["metabolome_marker"],
            ))

    def _add_integration(self, results: Dict[str, List[Any]]):
        """Add multi-omics integration sections."""
        if "procrustes" in results:
            r = results["procrustes"][0]
            stats = r.get("statistics", {}) if isinstance(r, dict) else {}
            m12 = stats.get("m12", "N/A")
            scale = stats.get("scale", "N/A")

            self.sections.append(ReportSection(
                title="Procrustes Analysis",
                content=f"Alignment of microbiome and metabolome configurations. m²={m12}, scale={scale}.",
                plot_data=r.get("plot_data") if isinstance(r, dict) else None,
                statistics=stats,
                order=self.SECTION_ORDER["procrustes"],
            ))

        if "mantel_test" in results:
            r = results["mantel_test"][0]
            stats = r.get("statistics", {}) if isinstance(r, dict) else {}
            corr = stats.get("correlation", stats.get("r", "N/A"))
            pval = stats.get("pvalue", stats.get("p", "N/A"))

            self.sections.append(ReportSection(
                title="Mantel Test",
                content=f"Distance matrix correlation: r={corr}, p={pval}. "
                        "Validates microbiome-metabolome co-variation independently of dimensionality reduction.",
                plot_data=r.get("plot_data") if isinstance(r, dict) else None,
                statistics=stats,
                order=self.SECTION_ORDER["mantel_test"],
            ))

        for module, title in [("sparse_cca", "Sparse CCA"),
                              ("rda", "RDA"),
                              ("o2pls", "O2PLS")]:
            if module in results:
                r = results[module][0]
                self.sections.append(ReportSection(
                    title=title,
                    content=f"{title} multi-omics integration analysis.",
                    plot_data=r.get("plot_data") if isinstance(r, dict) else None,
                    statistics=r.get("statistics") if isinstance(r, dict) else None,
                    order=self.SECTION_ORDER.get(module, 80),
                ))

    def _add_feature_level(self, results: Dict[str, List[Any]]):
        """Add feature-level analysis sections."""
        if "cross_correlation" in results:
            r = results["cross_correlation"][0]
            self.sections.append(ReportSection(
                title="Feature-level Cross-correlations",
                content="Spearman rank correlations between bacterial genera and metabolites.",
                plot_data=r.get("heatmap") or (r.get("plot_data") if isinstance(r, dict) else None),
                table_data=r.get("significant_pairs") if isinstance(r, dict) else None,
                order=self.SECTION_ORDER["cross_correlation"],
            ))

        if "network_sparcc" in results:
            r = results["network_sparcc"][0]
            self.sections.append(ReportSection(
                title="SparCC Network",
                content="Correlation network for microbiome taxa accounting for compositional effects.",
                order=self.SECTION_ORDER["network_sparcc"],
            ))

    def _add_conclusions(self, results: Dict[str, List[Any]]):
        """Add automated conclusions section."""
        conclusions = []

        # Check for significant integrations
        if "mantel_test" in results:
            r = results["mantel_test"][0]
            if isinstance(r, dict):
                stats = r.get("statistics", {})
                pval = stats.get("pvalue", stats.get("p", 1))
                if isinstance(pval, (int, float)) and pval < 0.05:
                    conclusions.append(
                        f"Mantel test confirmed significant microbiome-metabolome co-variation (p={pval:.4f})."
                    )

        # Check markers
        mb_sig = 0
        met_sig = 0
        if "microbiome_marker" in results:
            r = results["microbiome_marker"][0]
            if isinstance(r, dict):
                sig = r.get("significant_features", [])
                mb_sig = len(sig) if isinstance(sig, list) else 0
        if "metabolome_marker" in results:
            r = results["metabolome_marker"][0]
            if isinstance(r, dict):
                sig = r.get("significant_features", [])
                met_sig = len(sig) if isinstance(sig, list) else 0

        if mb_sig > 0 or met_sig > 0:
            conclusions.append(
                f"Marker discovery identified {mb_sig} microbiome and {met_sig} metabolome "
                "differential features."
            )

        if not conclusions:
            conclusions.append("Analysis completed. No significant findings detected in this dataset.")

        self.sections.append(ReportSection(
            title="Conclusions",
            content="\n".join(f"{i+1}. {c}" for i, c in enumerate(conclusions)),
            order=self.SECTION_ORDER["conclusions"],
        ))

    def _generate_summary(self, results: Dict[str, List[Any]]) -> Dict[str, Any]:
        """Generate a high-level summary."""
        summary = {
            "modules_executed": list(results.keys()),
            "n_modules": len(results),
        }

        # Count significant findings
        total_sig = 0
        for module, result_list in results.items():
            if "marker" in module:
                for r in result_list:
                    if isinstance(r, dict):
                        sig = r.get("significant_features", [])
                        total_sig += len(sig) if isinstance(sig, list) else 0

        summary["total_significant_features"] = total_sig
        return summary



from collections import defaultdict
