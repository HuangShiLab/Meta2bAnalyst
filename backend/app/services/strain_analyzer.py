"""
Meta2bAnalyst - Strain-Level Analyzer
Handles Strain2bScan and Tag2bMap output analysis.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist, squareform
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)


def parse_strain2bscan_output(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse Strain2bScan output into a structured DataFrame.

    Expected columns may include: species, strain, ANI, coverage, sample, abundance
    """
    # Standardize column names (case-insensitive)
    df.columns = [c.lower() for c in df.columns]
    return df


def filter_strains_by_ani(
    df: pd.DataFrame,
    min_ani: float = 95.0,
    max_ani: float = 100.0,
) -> pd.DataFrame:
    """Filter strain assignments by ANI threshold."""
    ani_col = [c for c in df.columns if "ani" in c]
    if ani_col:
        mask = (df[ani_col[0]] >= min_ani) & (df[ani_col[0]] <= max_ani)
        return df[mask].copy()
    return df.copy()


def filter_strains_by_coverage(
    df: pd.DataFrame,
    min_coverage: float = 0.8,
) -> pd.DataFrame:
    """Filter strain assignments by coverage threshold."""
    cov_col = [c for c in df.columns if "coverage" in c or "cov" in c]
    if cov_col:
        mask = df[cov_col[0]] >= min_coverage
        return df[mask].copy()
    return df.copy()


def run_strain_profile(
    df: pd.DataFrame,
    species: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], int]:
    """
    Generate strain profile for a target species.

    Returns:
        Tuple of (result_dict, strain_count)
    """
    params = parameters or {}
    min_ani = params.get("min_ani", 95.0)
    min_coverage = params.get("min_coverage", 0.8)
    
    # Filter by species if column exists
    species_col = [c for c in df.columns if "species" in c]
    if species_col:
        df_species = df[df[species_col[0]] == species].copy()
    else:
        df_species = df.copy()
    
    # Apply ANI and coverage filters
    df_species = filter_strains_by_ani(df_species, min_ani=min_ani)
    df_species = filter_strains_by_coverage(df_species, min_coverage=min_coverage)
    
    strain_count = len(df_species)
    
    # Extract strain information
    strain_col = [c for c in df_species.columns if "strain" in c]
    strain_names = df_species[strain_col[0]].tolist() if strain_col else []
    
    # Extract ANI and coverage stats
    ani_col = [c for c in df_species.columns if "ani" in c]
    cov_col = [c for c in df_species.columns if "coverage" in c]
    
    stats = {
        "species": species,
        "strain_count": strain_count,
        "strain_names": [str(s) for s in strain_names],
    }
    
    if ani_col:
        stats["ani"] = {
            "mean": float(df_species[ani_col[0]].mean()),
            "median": float(df_species[ani_col[0]].median()),
            "min": float(df_species[ani_col[0]].min()),
            "max": float(df_species[ani_col[0]].max()),
            "std": float(df_species[ani_col[0]].std()),
        }
    
    if cov_col:
        stats["coverage"] = {
            "mean": float(df_species[cov_col[0]].mean()),
            "median": float(df_species[cov_col[0]].median()),
            "min": float(df_species[cov_col[0]].min()),
            "max": float(df_species[cov_col[0]].max()),
            "std": float(df_species[cov_col[0]].std()),
        }
    
    return {"strain_profile": stats}, strain_count


def run_strain_comparison(
    df: pd.DataFrame,
    species: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compare strain profiles between groups or samples.

    Returns:
        Dict with comparison statistics
    """
    params = parameters or {}
    group_column = params.get("group_column")
    
    profile, strain_count = run_strain_profile(df, species, parameters)
    
    # If no group column, just return the profile
    if not group_column or group_column not in df.columns:
        return profile
    
    groups = df[group_column].dropna().unique().tolist()
    group_profiles = {}
    
    for group in groups:
        group_df = df[df[group_column] == group]
        group_profile, _ = run_strain_profile(group_df, species, parameters)
        group_profiles[str(group)] = group_profile["strain_profile"]
    
    return {
        "strain_profile": profile["strain_profile"],
        "group_profiles": group_profiles,
        "groups": [str(g) for g in groups],
    }


def run_ani_matrix(
    df: pd.DataFrame,
    species: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate ANI distance matrix between strains.

    Returns:
        Dict with ANI matrix and strain names
    """
    params = parameters or {}
    min_ani = params.get("min_ani", 95.0)
    
    # Filter by species
    species_col = [c for c in df.columns if "species" in c]
    if species_col:
        df_species = df[df[species_col[0]] == species].copy()
    else:
        df_species = df.copy()
    
    df_species = filter_strains_by_ani(df_species, min_ani=min_ani)
    
    strain_col = [c for c in df_species.columns if "strain" in c]
    if not strain_col:
        return {"error": "No strain column found in data"}
    
    strains = df_species[strain_col[0]].unique().tolist()
    
    # Build ANI matrix (simplified: pairwise ANI comparison)
    # In real implementation, this would use full ANI matrix from Strain2bScan
    n = len(strains)
    ani_matrix = np.zeros((n, n))
    
    ani_col = [c for c in df_species.columns if "ani" in c]
    if ani_col:
        # Use ANI values as similarity; convert to distance
        for i, strain_i in enumerate(strains):
            for j, strain_j in enumerate(strains):
                if i == j:
                    ani_matrix[i, j] = 100.0
                else:
                    # Simplified: average ANI for both strains
                    ani_i = df_species[df_species[strain_col[0]] == strain_i][ani_col[0]].mean()
                    ani_j = df_species[df_species[strain_col[0]] == strain_j][ani_col[0]].mean()
                    ani_matrix[i, j] = (ani_i + ani_j) / 2
    else:
        # Default: identity matrix if no ANI data
        np.fill_diagonal(ani_matrix, 100.0)
    
    # Convert similarity to distance
    dist_matrix = 100.0 - ani_matrix
    
    return {
        "species": species,
        "strains": [str(s) for s in strains],
        "ani_matrix": ani_matrix.tolist(),
        "distance_matrix": dist_matrix.tolist(),
        "strain_count": n,
    }


def run_strain_pcoa(
    df: pd.DataFrame,
    species: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run PCoA on strain-level ANI distances.

    Returns:
        Dict with PCoA coordinates
    """
    ani_result = run_ani_matrix(df, species, parameters)
    
    if "error" in ani_result:
        return ani_result
    
    dist_matrix = np.array(ani_result["distance_matrix"])
    strains = ani_result["strains"]
    
    # PCoA on distance matrix
    n = dist_matrix.shape[0]
    H = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * H @ (dist_matrix ** 2) @ H
    
    eigenvalues, eigenvectors = np.linalg.eigh(B)
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]
    
    positive_mask = eigenvalues > 0
    eigenvalues = eigenvalues[positive_mask][:3]
    eigenvectors = eigenvectors[:, positive_mask][:, :3]
    
    coordinates = eigenvectors * np.sqrt(eigenvalues)
    total_variance = np.sum(eigenvalues[eigenvalues > 0])
    variance_explained = [(e / total_variance) * 100 for e in eigenvalues] if total_variance > 0 else []
    
    return {
        "species": species,
        "strains": strains,
        "coordinates": {
            strain: coords.tolist()
            for strain, coords in zip(strains, coordinates)
        },
        "eigenvalues": eigenvalues.tolist(),
        "variance_explained": variance_explained,
    }
