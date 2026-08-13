"""
Meta2bAnalyst - Functional Analysis (KEGG Pathway Enrichment)
Implements KEGG KO mapping, hypergeometric enrichment testing,
and Plotly visualization for pathway analysis.
"""
import logging
import time
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.stats import fisher_exact, rankdata

logger = logging.getLogger(__name__)

# ─────────────────────────────── KEGG API & Caching

_KEGG_KO_CACHE: Dict[str, Optional[str]] = {}
_KEGG_LAST_REQUEST_TIME: float = 0.0
_KEGG_REQUEST_INTERVAL: float = 0.2  # 200ms between requests (5 req/sec)


def kegg_api_get_ko(feature_id: str) -> Optional[str]:
    """Query KEGG REST API for KO mapping with rate-limiting and caching.

    Args:
        feature_id: Feature identifier (e.g. species name or gene ID).

    Returns:
        KO identifier (e.g. 'K00001') or None if not found / API error.
    """
    global _KEGG_LAST_REQUEST_TIME

    # Check cache first
    if feature_id in _KEGG_KO_CACHE:
        return _KEGG_KO_CACHE[feature_id]

    # Rate limiting
    elapsed = time.time() - _KEGG_LAST_REQUEST_TIME
    if elapsed < _KEGG_REQUEST_INTERVAL:
        time.sleep(_KEGG_REQUEST_INTERVAL - elapsed)

    try:
        import urllib.request
        import urllib.error

        # Try find query (generic search)
        url = f"https://rest.kegg.jp/find/ko/{feature_id}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Meta2bAnalyst/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read().decode("utf-8")

        _KEGG_LAST_REQUEST_TIME = time.time()

        if not data or "K" not in data:
            _KEGG_KO_CACHE[feature_id] = None
            return None

        # Parse first KO hit
        for line in data.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].startswith("ko:"):
                ko_id = parts[0].replace("ko:", "").strip()
                _KEGG_KO_CACHE[feature_id] = ko_id
                return ko_id

        _KEGG_KO_CACHE[feature_id] = None
        return None

    except Exception as e:
        logger.warning(f"KEGG API lookup failed for {feature_id}: {e}")
        _KEGG_KO_CACHE[feature_id] = None
        return None


def get_mock_pathway_map() -> Dict[str, Dict[str, Any]]:
    """Return predefined mock KEGG pathways for demo/fallback purposes.

    Returns:
        Dict mapping pathway_id -> {name, ko_list}.
    """
    return {
        "ko00010": {
            "name": "Glycolysis / Gluconeogenesis",
            "ko_list": ["K00001", "K00002", "K00003", "K00134", "K00150", "K00873", "K00927", "K01623", "K01624", "K01803"],
        },
        "ko00020": {
            "name": "Citrate cycle (TCA cycle)",
            "ko_list": ["K00031", "K00030", "K00025", "K00026", "K00164", "K00174", "K00175", "K00234", "K00239", "K00240", "K00244", "K01681", "K01682", "K01647", "K01902", "K01903", "K01899", "K01900"],
        },
        "ko00030": {
            "name": "Pentose phosphate pathway",
            "ko_list": ["K00036", "K00033", "K01783", "K01807", "K01808", "K00615", "K00616", "K11440"],
        },
        "ko00190": {
            "name": "Oxidative phosphorylation",
            "ko_list": ["K00411", "K00412", "K00413", "K00414", "K00415", "K00416", "K00417", "K00418", "K00419", "K00420", "K02132", "K02133", "K02136", "K02137"],
        },
        "ko00230": {
            "name": "Purine metabolism",
            "ko_list": ["K00088", "K00758", "K00759", "K00760", "K00761", "K00762", "K00764", "K00856", "K00942", "K00944", "K01923", "K01933", "K01939", "K01945", "K11787"],
        },
        "ko00240": {
            "name": "Pyrimidine metabolism",
            "ko_list": ["K00074", "K00611", "K00758", "K00940", "K00942", "K01409", "K01465", "K01923", "K01937", "K01938"],
        },
        "ko00500": {
            "name": "Starch and sucrose metabolism",
            "ko_list": ["K00688", "K00693", "K00703", "K00705", "K01187", "K01193", "K01194", "K01208", "K01209"],
        },
        "ko00520": {
            "name": "Amino sugar and nucleotide sugar metabolism",
            "ko_list": ["K00730", "K00736", "K00790", "K00849", "K00973", "K00975", "K01784", "K02438"],
        },
        "ko00620": {
            "name": "Pyruvate metabolism",
            "ko_list": ["K00016", "K00024", "K00025", "K00026", "K00027", "K00028", "K00029", "K00116", "K00169", "K00170", "K00172", "K00174", "K00627", "K00873", "K01647", "K01681", "K01682", "K01895", "K01958", "K01959", "K01960"],
        },
        "ko00630": {
            "name": "Glyoxylate and dicarboxylate metabolism",
            "ko_list": ["K00024", "K00025", "K00026", "K00031", "K00116", "K00161", "K00162", "K00164", "K00174", "K00175", "K00600", "K00625", "K00626", "K01595", "K01610", "K01637", "K01638", "K01745", "K01847", "K01902", "K01903"],
        },
        "ko00640": {
            "name": "Propanoate metabolism",
            "ko_list": ["K00016", "K00022", "K00024", "K00134", "K00249", "K00634", "K00932", "K01692", "K01847", "K01908", "K01909"],
        },
        "ko00650": {
            "name": "Butanoate metabolism",
            "ko_list": ["K00022", "K00023", "K00024", "K00074", "K00232", "K00248", "K00634", "K00929", "K01034", "K01035", "K01036", "K01692", "K01895", "K01909"],
        },
        "ko00720": {
            "name": "Carbon fixation pathways in prokaryotes",
            "ko_list": ["K00024", "K00025", "K00026", "K00169", "K00170", "K00171", "K00172", "K00174", "K00175", "K00176", "K00177", "K00194", "K00195", "K00197", "K00239", "K00240", "K00241", "K00242", "K00244", "K00245", "K00246", "K00247", "K00625", "K00626", "K00925", "K01595", "K01601", "K01602", "K01902", "K01903", "K02437", "K03841", "K05282", "K14164", "K14165", "K14166", "K14167", "K14168", "K14169", "K14170", "K14171"],
        },
        "ko00910": {
            "name": "Nitrogen metabolism",
            "ko_list": ["K00370", "K00371", "K00372", "K00373", "K00374", "K00362", "K00363", "K00366", "K00367", "K00368", "K00369", "K00360", "K00361", "K02567", "K02568", "K02586", "K04561", "K10944", "K10945", "K10946"],
        },
        "ko02010": {
            "name": "ABC transporters",
            "ko_list": ["K01990", "K01992", "K01993", "K02003", "K02004", "K02005", "K02006", "K02007", "K02008", "K02009", "K02010", "K02011", "K02012", "K02013", "K02014", "K02015", "K02016", "K02017", "K02018", "K02019"],
        },
        "ko02020": {
            "name": "Two-component system",
            "ko_list": ["K02483", "K02488", "K02489", "K02490", "K02491", "K02492", "K02493", "K02494", "K02495", "K03406", "K03407", "K03408", "K03412", "K03413", "K03414", "K03415", "K03416", "K07636", "K07637", "K07638", "K07639", "K07640", "K07641", "K07642", "K07643", "K07644", "K07645", "K07646", "K07647", "K07648", "K07649", "K07650", "K07651", "K07652", "K07653", "K07654", "K07655", "K07656", "K07657", "K07658", "K07659", "K07660", "K07661", "K07662", "K07663", "K07664", "K07665", "K07666", "K07667", "K07668", "K07669", "K07670"],
        },
    }


# ─────────────────────────────── Enrichment Core


def hypergeometric_enrichment(
    significant_features: List[str],
    background_features: List[str],
    pathway_map: Dict[str, Dict[str, Any]],
    ko_mapping: Optional[Dict[str, Optional[str]]] = None,
) -> pd.DataFrame:
    """Perform hypergeometric enrichment (Fisher's exact test) for KEGG pathways.

    Args:
        significant_features: List of differentially abundant feature IDs.
        background_features: List of all background feature IDs.
        pathway_map: Dict {pathway_id: {name, ko_list}}.
        ko_mapping: Optional dict mapping feature_id -> KO. If None, features
            are treated as KO identifiers directly.

    Returns:
        DataFrame with columns:
            pathway_id, pathway_name, count, background_count, ratio,
            pvalue, padj, neg_log10_p, gene_ratio, bg_ratio.
    """
    sig_set = set(significant_features)
    bg_set = set(background_features)
    n_sig = len(sig_set)
    n_bg = len(bg_set)

    if n_sig == 0 or n_bg == 0:
        return pd.DataFrame()

    results = []
    ko_map = ko_mapping or {}

    for pathway_id, info in pathway_map.items():
        pathway_kos = set(info.get("ko_list", []))
        pathway_name = info.get("name", pathway_id)

        # Map features to KO
        if ko_mapping:
            sig_kos = {ko_map.get(f) for f in sig_set if ko_map.get(f) is not None}
            bg_kos = {ko_map.get(f) for f in bg_set if ko_map.get(f) is not None}
        else:
            sig_kos = sig_set
            bg_kos = bg_set

        overlap = sig_kos & pathway_kos
        bg_overlap = bg_kos & pathway_kos

        count = len(overlap)
        bg_count = len(bg_overlap)

        if bg_count == 0:
            continue

        # Contingency table:
        #           in_pathway  not_in_pathway
        # sig           a            b
        # bg            c            d
        a = count
        c = bg_count - count
        b = n_sig - count
        d = n_bg - n_sig - c

        if a < 0 or b < 0 or c < 0 or d < 0:
            continue

        try:
            _, pvalue = fisher_exact([[a, b], [c, d]], alternative="greater")
        except Exception:
            pvalue = 1.0

        ratio = count / n_sig if n_sig > 0 else 0.0
        bg_ratio = bg_count / n_bg if n_bg > 0 else 0.0

        results.append({
            "pathway_id": pathway_id,
            "pathway_name": pathway_name,
            "count": count,
            "background_count": bg_count,
            "ratio": ratio,
            "pvalue": pvalue,
            "gene_ratio": count / bg_count if bg_count > 0 else 0.0,
            "bg_ratio": bg_ratio,
        })

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)

    # BH-FDR correction
    pvalues = df["pvalue"].values
    n = len(pvalues)
    if n > 0:
        ranks = rankdata(pvalues, method="max")
        padj = np.minimum(pvalues * n / ranks, 1.0)
        df["padj"] = padj
    else:
        df["padj"] = pvalues

    df["neg_log10_p"] = -np.log10(df["pvalue"].replace(0, 1e-300))
    df["neg_log10_padj"] = -np.log10(df["padj"].replace(0, 1e-300))

    df = df.sort_values("pvalue")
    return df


# ─────────────────────────────── Plotly Visualizations


def plotly_pathway_bar(enrichment_df: pd.DataFrame, top_n: int = 15) -> dict:
    """Generate horizontal bar plot of top enriched pathways (-log10 p-value).

    Args:
        enrichment_df: Enrichment result DataFrame.
        top_n: Number of top pathways to display.

    Returns:
        Plotly figure JSON dict.
    """
    if enrichment_df.empty:
        return go.Figure().update_layout(title="No enrichment results to display").to_dict()

    df = enrichment_df.head(top_n).sort_values("neg_log10_p", ascending=True)

    colors = ["#d62728" if p < 0.05 else "#1f77b4" for p in df["pvalue"]]

    fig = go.Figure(
        data=[
            go.Bar(
                x=df["neg_log10_p"].values,
                y=df["pathway_name"].values,
                orientation="h",
                marker_color=colors,
                text=[f"p={p:.2e}" for p in df["pvalue"]],
                textposition="outside",
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "-log10(p): %{x:.2f}<br>"
                    "Count: %{customdata[0]}<br>"
                    "Gene Ratio: %{customdata[1]:.3f}<br>"
                    "<extra></extra>"
                ),
                customdata=np.stack([df["count"].values, df["gene_ratio"].values], axis=-1),
            )
        ]
    )

    fig.update_layout(
        title=f"Top {top_n} Enriched KEGG Pathways",
        xaxis_title="-log10(p-value)",
        yaxis_title="KEGG Pathway",
        template="plotly_white",
        margin=dict(l=250, r=40, t=60, b=40),
        height=max(400, top_n * 30),
    )
    return fig.to_dict()


def plotly_pathway_dot(enrichment_df: pd.DataFrame, top_n: int = 15) -> dict:
    """Generate dot plot of top enriched pathways.

    X-axis = Gene Ratio, Y-axis = Pathway, Size = Count, Color = -log10(p).

    Args:
        enrichment_df: Enrichment result DataFrame.
        top_n: Number of top pathways to display.

    Returns:
        Plotly figure JSON dict.
    """
    if enrichment_df.empty:
        return go.Figure().update_layout(title="No enrichment results to display").to_dict()

    df = enrichment_df.head(top_n).sort_values("neg_log10_p", ascending=True)

    fig = go.Figure(
        data=[
            go.Scatter(
                x=df["gene_ratio"].values,
                y=df["pathway_name"].values,
                mode="markers",
                marker=dict(
                    size=df["count"].values * 4 + 8,
                    color=df["neg_log10_p"].values,
                    colorscale="YlOrRd",
                    colorbar=dict(title="-log10(p)"),
                    showscale=True,
                ),
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Gene Ratio: %{x:.3f}<br>"
                    "Count: %{marker.size:.0f}<br>"
                    "-log10(p): %{marker.color:.2f}<br>"
                    "<extra></extra>"
                ),
            )
        ]
    )

    fig.update_layout(
        title=f"Top {top_n} Enriched KEGG Pathways (Dot Plot)",
        xaxis_title="Gene Ratio",
        yaxis_title="KEGG Pathway",
        template="plotly_white",
        margin=dict(l=250, r=100, t=60, b=40),
        height=max(400, top_n * 30),
    )
    return fig.to_dict()


# ─────────────────────────────── Main Runner


def run_pathway_analysis(
    df: pd.DataFrame,
    diff_result_data: Optional[Dict[str, Any]] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run KEGG pathway enrichment analysis on differentially abundant features.

    Args:
        df: Feature table (features x samples) — provides background feature list.
        diff_result_data: Prior differential analysis result dict containing
            'significant_features' list. If None, falls back to mock demo mode.
        parameters: Dict with keys:
            - test_method: 'hypergeometric' (default)
            - pvalue_threshold: significance cutoff (default 0.05)
            - use_kegg_api: bool, attempt KEGG API KO mapping (default True)
            - top_n_plot: number of pathways in plots (default 15)

    Returns:
        Dictionary with enrichment results, statistics, and Plotly figures.
    """
    params = parameters or {}
    test_method = params.get("test_method", "hypergeometric")
    pvalue_threshold = params.get("pvalue_threshold", 0.05)
    use_kegg_api = params.get("use_kegg_api", True)
    top_n_plot = params.get("top_n_plot", 15)

    background_features = list(df.index)

    # Extract significant features from prior differential job
    significant_features: List[str] = []
    if diff_result_data:
        sig = diff_result_data.get("significant_features", [])
        if isinstance(sig, list):
            significant_features = [
                f.get("feature", f) if isinstance(f, dict) else f
                for f in sig
            ]

    # KO mapping
    ko_mapping: Dict[str, Optional[str]] = {}
    kegg_api_available = False

    if use_kegg_api and significant_features:
        logger.info(f"Mapping {len(significant_features)} significant features to KEGG KO via API...")
        mapped = 0
        for feat in significant_features:
            ko = kegg_api_get_ko(feat)
            if ko:
                mapped += 1
            ko_mapping[feat] = ko
        kegg_api_available = mapped > 0
        logger.info(f"KEGG API mapping complete: {mapped}/{len(significant_features)} features mapped.")

    # If API failed or disabled, fall back to mock pathways
    if not kegg_api_available:
        logger.info("KEGG API unavailable or no mappings found. Using mock pathways for demo.")
        pathway_map = get_mock_pathway_map()
        # Generate synthetic KO mapping so some pathways show enrichment
        if not ko_mapping:
            for feat in background_features:
                # Deterministic pseudo-random assignment based on feature hash
                idx = hash(feat) % 100
                if idx < 50:
                    # Pick a random KO from mock pathways
                    all_kos = []
                    for p in pathway_map.values():
                        all_kos.extend(p["ko_list"])
                    ko_mapping[feat] = all_kos[idx % len(all_kos)] if all_kos else None
                else:
                    ko_mapping[feat] = None
    else:
        # Try to fetch real pathway map from KEGG (link ko -> pathway)
        # For simplicity, we still use mock pathways but filter by mapped KOs
        pathway_map = get_mock_pathway_map()

    # Run enrichment
    if test_method == "hypergeometric":
        enrichment_df = hypergeometric_enrichment(
            significant_features=significant_features,
            background_features=background_features,
            pathway_map=pathway_map,
            ko_mapping=ko_mapping if kegg_api_available else None,
        )
    else:
        enrichment_df = pd.DataFrame()

    # Build result
    sig_df = enrichment_df[enrichment_df["pvalue"] < pvalue_threshold] if not enrichment_df.empty else pd.DataFrame()

    bar_plot = plotly_pathway_bar(enrichment_df, top_n=top_n_plot)
    dot_plot = plotly_pathway_dot(enrichment_df, top_n=top_n_plot)

    result: Dict[str, Any] = {
        "test_method": test_method,
        "pvalue_threshold": pvalue_threshold,
        "n_significant_features": len(significant_features),
        "n_background_features": len(background_features),
        "kegg_api_used": kegg_api_available,
        "n_pathways_tested": len(pathway_map),
        "n_pathways_significant": len(sig_df),
        "enrichment_results": enrichment_df.to_dict(orient="records") if not enrichment_df.empty else [],
        "significant_pathways": sig_df.to_dict(orient="records") if not sig_df.empty else [],
        "plot_data": {
            "bar_plot": bar_plot,
            "dot_plot": dot_plot,
        },
    }

    return result
