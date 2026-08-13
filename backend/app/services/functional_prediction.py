"""
Meta2bAnalyst - Functional Prediction Module (PICRUSt2 / Tax4Fun Style)
Implements functional profiling from taxonomic abundance tables using
reference genome-based KO/Pathway prediction with quality metrics (NSTI).

Supports:
  - PICRUSt2-style: 16S/2bRAD taxonomic profiles → KO/Pathway abundance
  - Tax4Fun-style: Silva-based taxonomic profiles → KEGG functional predictions

References:
  - PICRUSt2: Douglas et al. 2020, Nat Biotechnol 38:685-688
  - Tax4Fun: Aßhauer et al. 2015, Bioinformatics 31:2882-2884
"""
import json
import logging
import random
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.spatial.distance import braycurtis, pdist, squareform
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

def _sanitize_json(obj):
    """Recursively convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, (np.bool_, np.bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return _sanitize_json(obj.to_dict(orient='records'))
    if isinstance(obj, pd.Series):
        return _sanitize_json(obj.to_dict())
    return obj


# ─────────────────────────────── Reference Database (Mock / Pre-computed)

# PICRUSt2-style: species / genus -> KO list with copy numbers
# This is a simplified reference. In production, load from picrust2/default_files/
_REF_PICRUSt2: Dict[str, Dict[str, Any]] = {}

# Tax4Fun-style: Silva taxon -> KO functional profile
_REF_TAX4FUN: Dict[str, Dict[str, Any]] = {}


def _load_reference_database() -> None:
    """Load or build mock reference database for functional prediction."""
    global _REF_PICRUSt2, _REF_TAX4FUN

    if _REF_PICRUSt2 and _REF_TAX4FUN:
        return

    # ── PICRUSt2-style reference: common gut microbes -> KO list ──
    # Based on typical genomic content of representative species
    _REF_PICRUSt2 = {
        # Bacteroidetes
        "Bacteroides": {
            "ko_profile": {
                "K00001": 2.1, "K00002": 1.8, "K00003": 1.5,  # Glycolysis
                "K00031": 1.2, "K00030": 1.0, "K00164": 1.5,  # TCA
                "K00688": 3.2, "K00693": 2.8, "K01187": 2.5,  # Starch/sucrose
                "K01990": 2.0, "K01992": 1.8, "K02003": 1.5,  # ABC transporters
                "K00370": 1.5, "K00371": 1.2,  # Nitrogen metabolism
                "K01623": 1.8, "K01624": 1.5,  # Glycolysis
                "K00873": 1.2, "K00927": 1.0,  # Glycolysis
                "K00150": 1.3,  # Pyruvate metabolism
                "K00234": 1.2, "K00239": 1.0,  # TCA
                "K01681": 1.1, "K01682": 1.0,  # TCA
                "K01783": 1.2, "K01807": 1.0,  # Pentose phosphate
                "K00615": 1.1, "K00616": 1.0,  # Pentose phosphate
                "K00036": 1.3, "K00033": 1.1,  # Pentose phosphate
                "K00411": 1.0, "K00412": 1.0, "K00413": 0.9,  # Oxidative phosphorylation
                "K02132": 1.0, "K02133": 1.0,  # Oxidative phosphorylation
                "K00088": 1.2, "K00758": 1.0, "K00942": 1.1,  # Purine metabolism
                "K00074": 1.1, "K00611": 1.0, "K00940": 1.0,  # Pyrimidine metabolism
                "K00730": 1.2, "K00736": 1.0, "K00973": 1.1,  # Amino sugar
                "K00016": 1.3, "K00024": 1.2, "K00116": 1.0,  # Pyruvate metabolism
                "K00169": 1.1, "K00170": 1.0,  # Carbon fixation
                "K00022": 1.0, "K00023": 1.0,  # Butanoate metabolism
                "K02483": 1.2, "K02488": 1.0,  # Two-component system
                "K00362": 1.0, "K00363": 1.0,  # Nitrogen metabolism
            },
            "nsti": 0.05,  # high quality reference
        },
        "Prevotella": {
            "ko_profile": {
                "K00001": 1.8, "K00002": 1.5, "K00003": 1.2,
                "K00688": 2.5, "K00693": 2.2, "K01187": 2.0,
                "K01990": 1.8, "K01992": 1.5,
                "K00370": 1.2, "K00371": 1.0,
                "K01623": 1.5, "K01624": 1.2,
                "K00031": 1.0, "K00164": 1.2,
                "K00730": 1.5, "K00736": 1.2,
                "K00016": 1.1, "K00024": 1.0,
                "K02483": 1.0, "K02488": 1.0,
                "K00362": 1.2, "K00363": 1.0,
            },
            "nsti": 0.08,
        },
        # Firmicutes
        "Lactobacillus": {
            "ko_profile": {
                "K00001": 2.0, "K00002": 1.8, "K00003": 1.5,
                "K00016": 2.5, "K00024": 2.0, "K00116": 1.8,  # Strong lactate fermentation
                "K01623": 1.8, "K01624": 1.5,
                "K00688": 1.5, "K01187": 1.2,
                "K01990": 1.2, "K01992": 1.0,
                "K00088": 1.5, "K00758": 1.2, "K00942": 1.3,
                "K00730": 1.0, "K00736": 1.0,
                "K02483": 1.5, "K02488": 1.2,  # Stress response
                "K00362": 0.8, "K00363": 0.7,
            },
            "nsti": 0.06,
        },
        "Bifidobacterium": {
            "ko_profile": {
                "K00001": 1.5, "K00002": 1.2, "K00003": 1.0,
                "K00688": 3.0, "K00693": 2.5, "K01187": 2.8,  # Fructan/starch metabolism
                "K00730": 2.0, "K00736": 1.8, "K00973": 1.5,  # Nucleotide sugar
                "K00088": 1.8, "K00758": 1.5, "K00942": 1.6,
                "K01990": 1.5, "K01992": 1.2,
                "K01623": 1.2, "K01624": 1.0,
                "K00016": 1.0, "K00024": 1.0,
                "K02483": 1.2, "K02488": 1.0,
            },
            "nsti": 0.07,
        },
        "Clostridium": {
            "ko_profile": {
                "K00001": 1.8, "K00002": 1.5, "K00003": 1.2,
                "K00022": 2.0, "K00023": 1.8, "K00024": 1.5,  # Butyrate production
                "K00016": 1.5, "K00116": 1.2,
                "K01623": 1.5, "K01624": 1.2,
                "K00031": 1.2, "K00164": 1.0,
                "K00370": 1.0, "K00371": 0.9,
                "K01990": 1.2, "K01992": 1.0,
                "K02483": 1.0, "K02488": 1.0,
            },
            "nsti": 0.10,
        },
        "Faecalibacterium": {
            "ko_profile": {
                "K00001": 1.5, "K00002": 1.2, "K00003": 1.0,
                "K00022": 1.8, "K00023": 1.5, "K00024": 1.2,  # Butyrate
                "K00016": 1.2, "K00116": 1.0,
                "K01623": 1.2, "K01624": 1.0,
                "K00031": 1.0, "K00164": 1.0,
                "K00370": 1.0, "K00371": 0.9,
                "K01990": 1.0, "K01992": 1.0,
            },
            "nsti": 0.09,
        },
        "Roseburia": {
            "ko_profile": {
                "K00001": 1.5, "K00002": 1.2, "K00003": 1.0,
                "K00022": 1.8, "K00023": 1.5, "K00024": 1.2,  # Butyrate
                "K00016": 1.2, "K00116": 1.0,
                "K01623": 1.2, "K01624": 1.0,
                "K00031": 1.0, "K00164": 1.0,
                "K01990": 1.0, "K01992": 1.0,
            },
            "nsti": 0.11,
        },
        "Ruminococcus": {
            "ko_profile": {
                "K00001": 1.8, "K00002": 1.5, "K00003": 1.2,
                "K00688": 2.0, "K00693": 1.8, "K01187": 1.5,  # Cellulose degradation
                "K01623": 1.5, "K01624": 1.2,
                "K00016": 1.0, "K00024": 1.0,
                "K00031": 1.0, "K00164": 1.0,
                "K01990": 1.2, "K01992": 1.0,
            },
            "nsti": 0.08,
        },
        # Proteobacteria
        "Escherichia": {
            "ko_profile": {
                "K00001": 2.0, "K00002": 1.8, "K00003": 1.5,
                "K00031": 1.5, "K00030": 1.2, "K00164": 1.5,  # Complete TCA
                "K01623": 1.8, "K01624": 1.5,
                "K00016": 1.5, "K00024": 1.2, "K00116": 1.0,
                "K01990": 2.0, "K01992": 1.8, "K02003": 1.5,  # Many ABC transporters
                "K00088": 1.5, "K00758": 1.2, "K00942": 1.3,
                "K00074": 1.2, "K00611": 1.0, "K00940": 1.0,
                "K00730": 1.2, "K00736": 1.0,
                "K00370": 1.2, "K00371": 1.0, "K00362": 1.0, "K00363": 1.0,
                "K02483": 1.5, "K02488": 1.2,  # Many two-component systems
                "K00411": 1.0, "K00412": 1.0, "K00413": 1.0,
                "K02132": 1.0, "K02133": 1.0,
            },
            "nsti": 0.03,  # very well studied
        },
        "Akkermansia": {
            "ko_profile": {
                "K01187": 3.0, "K01193": 2.5, "K01194": 2.0,  # Mucin degradation
                "K00730": 2.0, "K00736": 1.8,  # Nucleotide sugar
                "K00001": 1.2, "K00002": 1.0, "K00003": 1.0,
                "K01623": 1.0, "K01624": 1.0,
                "K01990": 1.2, "K01992": 1.0,
                "K00016": 1.0, "K00024": 1.0,
            },
            "nsti": 0.12,  # less reference genomes
        },
        # Actinobacteria
        "Collinsella": {
            "ko_profile": {
                "K00001": 1.2, "K00002": 1.0, "K00003": 1.0,
                "K00730": 1.5, "K00736": 1.2, "K00973": 1.0,
                "K01623": 1.0, "K01624": 1.0,
                "K01990": 1.0, "K01992": 1.0,
            },
            "nsti": 0.14,
        },
    }

    # ── Tax4Fun-style reference: Silva taxon -> KO profile ──
    # Similar but at higher taxonomic level (phylum/class)
    _REF_TAX4FUN = {
        "Bacteroidetes": _REF_PICRUSt2["Bacteroides"]["ko_profile"],
        "Firmicutes": _REF_PICRUSt2["Lactobacillus"]["ko_profile"],
        "Proteobacteria": _REF_PICRUSt2["Escherichia"]["ko_profile"],
        "Actinobacteria": _REF_PICRUSt2["Bifidobacterium"]["ko_profile"],
        "Verrucomicrobia": _REF_PICRUSt2["Akkermansia"]["ko_profile"],
    }

    logger.info(
        f"Reference DB loaded: {len(_REF_PICRUSt2)} PICRUSt2 taxa, "
        f"{len(_REF_TAX4FUN)} Tax4Fun taxa"
    )


def _get_taxon_match(taxon_name: str, db_type: str = "picrust2") -> Optional[str]:
    """Find best matching reference taxon for a given feature name."""
    _load_reference_database()

    taxon_lower = taxon_name.lower()

    if db_type == "picrust2":
        ref_db = _REF_PICRUSt2
        # Direct match
        for ref_taxon in ref_db:
            if ref_taxon.lower() in taxon_lower or taxon_lower in ref_taxon.lower():
                return ref_taxon
        # Genus-level fallback: extract first word
        genus = taxon_name.split()[0] if taxon_name else ""
        for ref_taxon in ref_db:
            if ref_taxon.lower() == genus.lower():
                return ref_taxon
    else:
        ref_db = _REF_TAX4FUN
        for ref_taxon in ref_db:
            if ref_taxon.lower() in taxon_lower or taxon_lower in ref_taxon.lower():
                return ref_taxon

    return None


# ─────────────────────────────── Pathway Definitions (KEGG)

_KEGG_PATHWAYS: Dict[str, Dict[str, Any]] = {
    "ko00010": {"name": "Glycolysis / Gluconeogenesis", "ko_list": ["K00001", "K00002", "K00003", "K00134", "K00150", "K00873", "K00927", "K01623", "K01624", "K01803"]},
    "ko00020": {"name": "Citrate cycle (TCA cycle)", "ko_list": ["K00031", "K00030", "K00025", "K00026", "K00164", "K00174", "K00175", "K00234", "K00239", "K00240", "K00244", "K01681", "K01682", "K01647", "K01902", "K01903", "K01899", "K01900"]},
    "ko00030": {"name": "Pentose phosphate pathway", "ko_list": ["K00036", "K00033", "K01783", "K01807", "K01808", "K00615", "K00616", "K11440"]},
    "ko00190": {"name": "Oxidative phosphorylation", "ko_list": ["K00411", "K00412", "K00413", "K00414", "K00415", "K00416", "K00417", "K00418", "K00419", "K00420", "K02132", "K02133", "K02136", "K02137"]},
    "ko00230": {"name": "Purine metabolism", "ko_list": ["K00088", "K00758", "K00759", "K00760", "K00761", "K00762", "K00764", "K00856", "K00942", "K00944", "K01923", "K01933", "K01939", "K01945", "K11787"]},
    "ko00240": {"name": "Pyrimidine metabolism", "ko_list": ["K00074", "K00611", "K00758", "K00940", "K00942", "K01409", "K01465", "K01923", "K01937", "K01938"]},
    "ko00500": {"name": "Starch and sucrose metabolism", "ko_list": ["K00688", "K00693", "K00703", "K00705", "K01187", "K01193", "K01194", "K01208", "K01209"]},
    "ko00520": {"name": "Amino sugar and nucleotide sugar metabolism", "ko_list": ["K00730", "K00736", "K00790", "K00849", "K00973", "K00975", "K01784", "K02438"]},
    "ko00620": {"name": "Pyruvate metabolism", "ko_list": ["K00016", "K00024", "K00025", "K00026", "K00027", "K00028", "K00029", "K00116", "K00169", "K00170", "K00172", "K00174", "K00627", "K00873", "K01647", "K01681", "K01682", "K01895", "K01958", "K01959", "K01960"]},
    "ko00630": {"name": "Glyoxylate and dicarboxylate metabolism", "ko_list": ["K00024", "K00025", "K00026", "K00031", "K00116", "K00161", "K00162", "K00164", "K00174", "K00175", "K00600", "K00625", "K00626", "K01595", "K01610", "K01637", "K01638", "K01745", "K01847", "K01902", "K01903"]},
    "ko00640": {"name": "Propanoate metabolism", "ko_list": ["K00016", "K00022", "K00024", "K00134", "K00249", "K00634", "K00932", "K01692", "K01847", "K01908", "K01909"]},
    "ko00650": {"name": "Butanoate metabolism", "ko_list": ["K00022", "K00023", "K00024", "K00074", "K00232", "K00248", "K00634", "K00929", "K01034", "K01035", "K01036", "K01692", "K01895", "K01909"]},
    "ko00720": {"name": "Carbon fixation pathways in prokaryotes", "ko_list": ["K00024", "K00025", "K00026", "K00169", "K00170", "K00171", "K00172", "K00174", "K00175", "K00176", "K00177", "K00194", "K00195", "K00197", "K00239", "K00240", "K00241", "K00242", "K00244", "K00245", "K00246", "K00247", "K00625", "K00626", "K00925", "K01595", "K01601", "K01602", "K01902", "K01903", "K02437", "K03841", "K05282", "K14164", "K14165", "K14166", "K14167", "K14168", "K14169", "K14170", "K14171"]},
    "ko00910": {"name": "Nitrogen metabolism", "ko_list": ["K00370", "K00371", "K00372", "K00373", "K00374", "K00362", "K00363", "K00366", "K00367", "K00368", "K00369", "K00360", "K00361", "K02567", "K02568", "K02586", "K04561", "K10944", "K10945", "K10946"]},
    "ko02010": {"name": "ABC transporters", "ko_list": ["K01990", "K01992", "K01993", "K02003", "K02004", "K02005", "K02006", "K02007", "K02008", "K02009", "K02010", "K02011", "K02012", "K02013", "K02014", "K02015", "K02016", "K02017", "K02018", "K02019"]},
    "ko02020": {"name": "Two-component system", "ko_list": ["K02483", "K02488", "K02489", "K02490", "K02491", "K02492", "K02493", "K02494", "K02495", "K03406", "K03407", "K03408", "K03412", "K03413", "K03414", "K03415", "K03416", "K07636", "K07637", "K07638", "K07639", "K07640", "K07641", "K07642", "K07643", "K07644", "K07645", "K07646", "K07647", "K07648", "K07649", "K07650", "K07651", "K07652", "K07653", "K07654", "K07655", "K07656", "K07657", "K07658", "K07659", "K07660", "K07661", "K07662", "K07663", "K07664", "K07665", "K07666", "K07667", "K07668", "K07669", "K07670"]},
}


# ─────────────────────────────── Core Prediction Algorithms

def predict_ko_abundance(
    df: pd.DataFrame,
    method: str = "picrust2",
    normalization: str = "copy_number",
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Predict KO (KEGG Orthology) functional abundance from taxonomic profiles.

    Args:
        df: Feature table (features x samples) with taxonomic abundances.
        method: 'picrust2' or 'tax4fun'.
        normalization: 'copy_number' (divide by copy number) or 'none'.

    Returns:
        ko_abundance: KO x samples DataFrame (predicted functional profile).
        metadata: Taxon mapping metadata DataFrame.
        quality_metrics: Dict with NSTI, coverage, etc.
    """
    _load_reference_database()

    features = list(df.index)
    samples = list(df.columns)

    # Map each feature to reference taxon
    taxon_matches: Dict[str, Optional[str]] = {}
    nsti_values: List[float] = []
    matched_kos: Dict[str, Dict[str, float]] = {}  # feature -> {ko: copy_number}

    for feat in features:
        match = _get_taxon_match(feat, method)
        taxon_matches[feat] = match

        if match:
            ref = _REF_PICRUSt2.get(match) if method == "picrust2" else _REF_TAX4FUN.get(match)
            if ref:
                ko_prof = ref.get("ko_profile", {})
                matched_kos[feat] = ko_prof
                nsti = ref.get("nsti", 0.15)
                nsti_values.append(nsti)
        else:
            # Unmatched taxon: add penalty NSTI
            nsti_values.append(0.25)  # > 0.15 means low quality prediction

    n_matched = len(matched_kos)
    n_total = len(features)
    coverage = n_matched / n_total if n_total > 0 else 0.0

    mean_nsti = np.mean(nsti_values) if nsti_values else 0.25
    weighted_nsti = 0.0
    if nsti_values:
        # Weight by sample total abundance
        sample_totals = df.sum(axis=0)
        weights = []
        for feat in features:
            match = taxon_matches[feat]
            if match:
                ref = _REF_PICRUSt2.get(match) if method == "picrust2" else _REF_TAX4FUN.get(match)
                nsti = ref.get("nsti", 0.15) if ref else 0.25
            else:
                nsti = 0.25
            # Average across samples for simplicity
            weights.append(nsti)
        weighted_nsti = np.average(nsti_values, weights=[df.loc[f].sum() for f in features])

    # Build KO abundance matrix
    all_kos: set = set()
    for ko_prof in matched_kos.values():
        all_kos.update(ko_prof.keys())

    ko_abundance = pd.DataFrame(0.0, index=sorted(all_kos), columns=samples)

    for feat in features:
        if feat not in matched_kos:
            continue

        ko_prof = matched_kos[feat]
        feat_abundance = df.loc[feat]

        for ko, copy_number in ko_prof.items():
            if ko not in ko_abundance.index:
                continue

            if normalization == "copy_number":
                # Divide by copy number to get per-genome equivalent
                ko_abundance.loc[ko] += feat_abundance / copy_number
            else:
                ko_abundance.loc[ko] += feat_abundance * copy_number

    # Metadata about predictions
    metadata = pd.DataFrame({
        "feature": features,
        "matched_taxon": [taxon_matches.get(f) for f in features],
        "nsti": [nsti_values[i] if i < len(nsti_values) else 0.25 for i in range(len(features))],
        "has_ko_profile": [f in matched_kos for f in features],
    })

    quality_metrics = {
        "method": method,
        "n_features": n_total,
        "n_matched": n_matched,
        "coverage": round(coverage, 3),
        "mean_nsti": round(mean_nsti, 3),
        "weighted_nsti": round(weighted_nsti, 3),
        "n_ko_predicted": len(all_kos),
        "normalization": normalization,
    }

    logger.info(
        f"Functional prediction: method={method}, coverage={coverage:.1%}, "
        f"NSTI={mean_nsti:.3f}, KOs={len(all_kos)}"
    )

    return ko_abundance, metadata, quality_metrics


def aggregate_pathway_abundance(
    ko_abundance: pd.DataFrame,
    pathway_map: Optional[Dict[str, Dict[str, Any]]] = None,
    aggregation: str = "sum",
) -> pd.DataFrame:
    """Aggregate KO abundances into KEGG pathway-level abundances.

    Args:
        ko_abundance: KO x samples DataFrame.
        pathway_map: Dict {pathway_id: {name, ko_list}}. Uses default if None.
        aggregation: 'sum' or 'mean' or 'median'.

    Returns:
        Pathway x samples DataFrame.
    """
    if pathway_map is None:
        pathway_map = _KEGG_PATHWAYS

    pathways = []
    for pw_id, info in pathway_map.items():
        ko_list = info.get("ko_list", [])
        if not ko_list:
            continue

        # Intersect with available KOs
        available_kos = [ko for ko in ko_list if ko in ko_abundance.index]
        if not available_kos:
            continue

        pw_abund = ko_abundance.loc[available_kos]

        if aggregation == "sum":
            pw_total = pw_abund.sum(axis=0)
        elif aggregation == "mean":
            pw_total = pw_abund.mean(axis=0)
        elif aggregation == "median":
            pw_total = pw_abund.median(axis=0)
        else:
            pw_total = pw_abund.sum(axis=0)

        pathways.append({
            "pathway_id": pw_id,
            "pathway_name": info.get("name", pw_id),
            "n_ko_total": len(ko_list),
            "n_ko_available": len(available_kos),
            "completeness": len(available_kos) / len(ko_list) if ko_list else 0,
            **{col: pw_total[col] for col in ko_abundance.columns},
        })

    pathway_df = pd.DataFrame(pathways)
    if not pathway_df.empty:
        pathway_df = pathway_df.set_index("pathway_id")
    return pathway_df


def normalize_ko_abundance(ko_abundance: pd.DataFrame, method: str = "relabund") -> pd.DataFrame:
    """Normalize KO abundance table.

    Args:
        ko_abundance: KO x samples DataFrame.
        method: 'relabund' (per-sample relative abundance) or 'tss' (total sum scaling).

    Returns:
        Normalized KO abundance DataFrame.
    """
    if method == "relabund":
        return ko_abundance.div(ko_abundance.sum(axis=0), axis=1)
    elif method == "tss":
        total = ko_abundance.sum(axis=0)
        return ko_abundance.div(total, axis=1) * 1000000  # CPM-like
    else:
        return ko_abundance


# ─────────────────────────────── Statistical Comparison (Group-level)

def compare_pathway_abundance(
    pathway_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    test: str = "wilcoxon",
) -> pd.DataFrame:
    """Compare pathway abundance between two groups.

    Args:
        pathway_df: Pathway x samples DataFrame (numeric columns only).
        metadata_df: Metadata DataFrame with sample index and group_column.
        group_column: Column name for grouping.
        test: 'wilcoxon', 'ttest', or 'kruskal'.

    Returns:
        DataFrame with pathway_id, pathway_name, mean_group1, mean_group2, log2fc, pvalue, padj.
    """
    from scipy.stats import kruskal, mannwhitneyu, ttest_ind

    sample_cols = [c for c in pathway_df.columns if c not in
                   ["pathway_name", "n_ko_total", "n_ko_available", "completeness"]]

    groups = metadata_df[group_column].dropna().unique().tolist()
    if len(groups) < 2:
        logger.warning(f"Need >=2 groups for comparison, got {len(groups)}")
        return pd.DataFrame()

    g1, g2 = groups[0], groups[1]
    s1 = metadata_df[metadata_df[group_column] == g1].index.intersection(sample_cols)
    s2 = metadata_df[metadata_df[group_column] == g2].index.intersection(sample_cols)

    results = []
    for pw_id in pathway_df.index:
        row = pathway_df.loc[pw_id]
        v1 = row[s1].dropna().values.astype(float)
        v2 = row[s2].dropna().values.astype(float)

        if len(v1) < 2 or len(v2) < 2:
            continue

        mean1, mean2 = v1.mean(), v2.mean()
        log2fc = np.log2((mean2 + 1e-6) / (mean1 + 1e-6))

        try:
            if test == "wilcoxon":
                _, pvalue = mannwhitneyu(v1, v2, alternative="two-sided")
            elif test == "ttest":
                _, pvalue = ttest_ind(v1, v2)
            else:
                _, pvalue = kruskal(v1, v2)
        except Exception:
            pvalue = 1.0

        results.append({
            "pathway_id": pw_id,
            "pathway_name": row.get("pathway_name", pw_id),
            "mean_group1": mean1,
            "mean_group2": mean2,
            "log2fc": log2fc,
            "pvalue": pvalue,
        })

    if not results:
        return pd.DataFrame()

    df_res = pd.DataFrame(results)
    # BH-FDR
    pvals = df_res["pvalue"].values
    n = len(pvals)
    if n > 0:
        from scipy.stats import rankdata
        ranks = rankdata(pvals, method="max")
        padj = np.minimum(pvals * n / ranks, 1.0)
        df_res["padj"] = padj
    else:
        df_res["padj"] = pvals

    return df_res.sort_values("pvalue")


# ─────────────────────────────── Plotly Visualizations

def plotly_ko_heatmap(ko_abundance: pd.DataFrame, top_n: int = 50) -> dict:
    """Generate heatmap of top KO abundances across samples.

    Args:
        ko_abundance: KO x samples DataFrame.
        top_n: Number of top KOs by mean abundance to display.

    Returns:
        Plotly figure JSON dict.
    """
    if ko_abundance.empty:
        return go.Figure().update_layout(title="No KO data available").to_dict()

    # Select top KOs by mean abundance
    ko_means = ko_abundance.mean(axis=1).sort_values(ascending=False)
    top_kos = ko_means.head(top_n).index.tolist()
    df_plot = ko_abundance.loc[top_kos]

    # Normalize per sample for visualization
    df_norm = df_plot.div(df_plot.sum(axis=0), axis=1)

    fig = px.imshow(
        df_norm.values,
        x=list(df_norm.columns),
        y=list(df_norm.index),
        color_continuous_scale="YlOrRd",
        aspect="auto",
        title=f"Top {top_n} KO Abundance Heatmap (per-sample normalized)",
    )
    fig.update_layout(
        xaxis_title="Sample",
        yaxis_title="KEGG Orthology (KO)",
        template="plotly_white",
        height=max(400, top_n * 18),
        margin=dict(l=150, r=40, t=60, b=100),
    )
    return fig.to_dict()


def plotly_pathway_bar(pathway_df: pd.DataFrame, top_n: int = 20) -> dict:
    """Generate horizontal bar plot of top pathway abundances.

    Args:
        pathway_df: Pathway x samples DataFrame.
        top_n: Number of top pathways by mean abundance.

    Returns:
        Plotly figure JSON dict.
    """
    if pathway_df.empty:
        return go.Figure().update_layout(title="No pathway data available").to_dict()

    # Get numeric sample columns
    numeric_cols = [c for c in pathway_df.columns if c not in
                    ["pathway_name", "n_ko_total", "n_ko_available", "completeness"]]

    pw_means = pathway_df[numeric_cols].mean(axis=1).sort_values(ascending=False)
    top_pws = pw_means.head(top_n)

    names = [pathway_df.loc[pw, "pathway_name"] if "pathway_name" in pathway_df.columns else pw
             for pw in top_pws.index]

    fig = go.Figure(
        data=[go.Bar(
            x=top_pws.values,
            y=names,
            orientation="h",
            marker_color="#2ca02c",
            text=[f"{v:.1f}" for v in top_pws.values],
            textposition="outside",
        )]
    )
    fig.update_layout(
        title=f"Top {top_n} Pathway Abundances",
        xaxis_title="Mean Abundance",
        yaxis_title="KEGG Pathway",
        template="plotly_white",
        height=max(400, top_n * 25),
        margin=dict(l=300, r=80, t=60, b=40),
    )
    return fig.to_dict()


def plotly_pathway_pca(pathway_df: pd.DataFrame, metadata_df: Optional[pd.DataFrame] = None,
                       group_column: Optional[str] = None) -> dict:
    """Generate PCA plot of pathway profiles.

    Args:
        pathway_df: Pathway x samples DataFrame.
        metadata_df: Optional metadata for coloring.
        group_column: Column for group colors.

    Returns:
        Plotly figure JSON dict.
    """
    numeric_cols = [c for c in pathway_df.columns if c not in
                    ["pathway_name", "n_ko_total", "n_ko_available", "completeness"]]
    X = pathway_df[numeric_cols].T.values

    if X.shape[0] < 2 or X.shape[1] < 2:
        return go.Figure().update_layout(title="Insufficient samples for PCA").to_dict()

    # Standardize and PCA
    X_std = StandardScaler().fit_transform(X)
    pca = PCA(n_components=2)
    coords = pca.fit_transform(X_std)

    explained = pca.explained_variance_ratio_ * 100

    df_plot = pd.DataFrame({
        "PC1": coords[:, 0],
        "PC2": coords[:, 1],
        "Sample": numeric_cols,
    })

    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        df_plot["Group"] = [str(metadata_df.loc[s, group_column]) if s in metadata_df.index else "Unknown"
                            for s in numeric_cols]
        fig = px.scatter(
            df_plot, x="PC1", y="PC2", color="Group",
            title=f"Pathway PCA (PC1 {explained[0]:.1f}%, PC2 {explained[1]:.1f}%)",
            hover_data=["Sample"],
        )
    else:
        fig = px.scatter(
            df_plot, x="PC1", y="PC2",
            title=f"Pathway PCA (PC1 {explained[0]:.1f}%, PC2 {explained[1]:.1f}%)",
            hover_data=["Sample"],
        )

    fig.update_layout(template="plotly_white", height=500, width=600)
    return fig.to_dict()


def plotly_functional_volcano(diff_df: pd.DataFrame, group1: str = "Group1", group2: str = "Group2") -> dict:
    """Generate volcano plot for differential pathway abundance.

    Args:
        diff_df: Result from compare_pathway_abundance().
        group1, group2: Group labels for axis titles.

    Returns:
        Plotly figure JSON dict.
    """
    if diff_df.empty:
        return go.Figure().update_layout(title="No differential pathway data").to_dict()

    diff_df = diff_df.copy()
    diff_df["neg_log10_p"] = -np.log10(diff_df["pvalue"].replace(0, 1e-300))
    diff_df["significant"] = diff_df["padj"] < 0.05

    colors = ["#d62728" if sig else "#1f77b4" for sig in diff_df["significant"]]

    fig = go.Figure(
        data=[go.Scatter(
            x=diff_df["log2fc"].values,
            y=diff_df["neg_log10_p"].values,
            mode="markers+text",
            text=diff_df["pathway_name"].values,
            textposition="top center",
            textfont=dict(size=8),
            marker=dict(color=colors, size=10, opacity=0.7),
            hovertemplate="<b>%{text}</b><br>log2FC: %{x:.3f}<br>-log10(p): %{y:.2f}<extra></extra>",
        )]
    )
    fig.update_layout(
        title=f"Differential Pathway Abundance: {group2} vs {group1}",
        xaxis_title=f"log2FC ({group2} / {group1})",
        yaxis_title="-log10(p-value)",
        template="plotly_white",
        height=500,
        width=600,
        shapes=[
            dict(type="line", x0=-1, x1=-1, y0=0, y1=max(diff_df["neg_log10_p"]) * 1.1,
                 line=dict(color="gray", dash="dash")),
            dict(type="line", x0=1, x1=1, y0=0, y1=max(diff_df["neg_log10_p"]) * 1.1,
                 line=dict(color="gray", dash="dash")),
            dict(type="line", x0=min(diff_df["log2fc"]) * 1.1, x1=max(diff_df["log2fc"]) * 1.1,
                 y0=-np.log10(0.05), y1=-np.log10(0.05),
                 line=dict(color="gray", dash="dash")),
        ],
    )
    return fig.to_dict()


# ─────────────────────────────── Main Runner (API-compatible)

def run_functional_prediction(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run complete functional prediction pipeline (PICRUSt2/Tax4Fun style).

    Args:
        df: Feature table (features x samples).
        metadata_df: Optional metadata DataFrame for group comparison.
        parameters: Dict with keys:
            - method: 'picrust2' or 'tax4fun' (default 'picrust2')
            - normalization: 'copy_number' or 'none' (default 'copy_number')
            - ko_normalization: 'relabund' or 'tss' or 'none' (default 'relabund')
            - aggregation: 'sum' or 'mean' (default 'sum')
            - group_column: metadata column for differential comparison
            - diff_test: 'wilcoxon', 'ttest', 'kruskal' (default 'wilcoxon')
            - top_n_ko: int for heatmap (default 50)
            - top_n_pathway: int for bar plot (default 20)
            - do_differential: bool (default True if metadata and group_column provided)

    Returns:
        Dict with ko_abundance, pathway_abundance, quality_metrics, plots, and differential results.
    """
    params = parameters or {}
    method = params.get("method", "picrust2")
    normalization = params.get("normalization", "copy_number")
    ko_normalization = params.get("ko_normalization", "relabund")
    aggregation = params.get("aggregation", "sum")
    group_column = params.get("group_column")
    diff_test = params.get("diff_test", "wilcoxon")
    top_n_ko = params.get("top_n_ko", 50)
    top_n_pathway = params.get("top_n_pathway", 20)
    do_differential = params.get("do_differential", metadata_df is not None and group_column is not None)

    logger.info(f"Starting functional prediction: method={method}, normalization={normalization}")

    # 1. Predict KO abundance
    ko_abundance, taxon_metadata, quality_metrics = predict_ko_abundance(
        df, method=method, normalization=normalization
    )

    # 2. Normalize KO abundance
    if ko_normalization != "none":
        ko_abundance = normalize_ko_abundance(ko_abundance, method=ko_normalization)

    # 3. Aggregate to pathways
    pathway_abundance = aggregate_pathway_abundance(ko_abundance, aggregation=aggregation)

    # 4. Differential comparison
    diff_results = {}
    if do_differential and metadata_df is not None and group_column:
        if group_column in metadata_df.columns:
            diff_df = compare_pathway_abundance(
                pathway_abundance, metadata_df, group_column, test=diff_test
            )
            if not diff_df.empty:
                diff_results = {
                    "n_significant": int((diff_df["padj"] < 0.05).sum()),
                    "pathway_table": diff_df.to_dict(orient="records"),
                    "volcano_plot": plotly_functional_volcano(diff_df),
                }
            else:
                diff_results = {"n_significant": 0, "pathway_table": [], "volcano_plot": {}}
        else:
            logger.warning(f"group_column '{group_column}' not found in metadata")

    # 5. Generate plots
    plots = {
        "ko_heatmap": plotly_ko_heatmap(ko_abundance, top_n=top_n_ko),
        "pathway_bar": plotly_pathway_bar(pathway_abundance, top_n=top_n_pathway),
        "pathway_pca": plotly_pathway_pca(pathway_abundance, metadata_df, group_column),
    }

    # 6. Build result dict
    result = _sanitize_json({
        "method": method,
        "quality_metrics": quality_metrics,
        "ko_abundance": ko_abundance.to_dict(orient="split") if not ko_abundance.empty else {},
        "pathway_abundance": pathway_abundance.reset_index().to_dict(orient="records")
        if not pathway_abundance.empty else [],
        "taxon_metadata": taxon_metadata.to_dict(orient="records"),
        "plots": plots,
        "differential": diff_results,
    })

    logger.info("Functional prediction complete")
    return result
