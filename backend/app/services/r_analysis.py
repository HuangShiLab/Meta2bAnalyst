"""
Meta2bAnalyst - R Analysis Integration (rpy2 optional)
Provides wrappers for R-based statistical analyses.
"""
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

R_AVAILABLE = False
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter
    from rpy2.robjects.packages import importr
    R_AVAILABLE = True
    logger.info("rpy2 is available for R integration")
except ImportError:
    logger.warning("rpy2 not installed. R-based analyses will be unavailable.")


def rpy2_available() -> bool:
    """Check if rpy2 is available."""
    return R_AVAILABLE


def run_r_script(script_path: Path, args: List[str]) -> subprocess.CompletedProcess:
    """Run an R script via subprocess as fallback."""
    cmd = ["Rscript", str(script_path)] + args
    logger.info(f"Running R script: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"R script failed: {result.stderr}")
        raise RuntimeError(f"R script failed: {result.stderr}")
    return result


def run_deseq2(
    count_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    design_formula: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run DESeq2 differential abundance analysis via R.

    Falls back to Python implementation if rpy2 is unavailable.
    """
    if not R_AVAILABLE:
        logger.warning("rpy2 not available, returning placeholder DESeq2 results")
        return {
            "method": "DESeq2",
            "status": "unavailable",
            "message": "rpy2 is not installed. DESeq2 requires R integration.",
        }
    
    try:
        with localconverter(ro.default_converter + pandas2ri.converter):
            # Import R packages
            deseq2 = importr("DESeq2")
            
            # Convert pandas DataFrames to R
            r_counts = ro.conversion.py2rpy(count_df.T)  # DESeq2 expects samples as columns
            r_metadata = ro.conversion.py2rpy(metadata_df)
            
            # Create DESeqDataSet
            formula = design_formula or f"~ {group_column}"
            dds = deseq2.DESeqDataSetFromMatrix(
                countData=r_counts,
                colData=r_metadata,
                design=ro.Formula(formula),
            )
            
            # Run DESeq2
            dds = deseq2.DESeq(dds)
            
            # Get results
            results_r = deseq2.results(dds)
            results_df = ro.conversion.rpy2py(results_r)
            
            return {
                "method": "DESeq2",
                "status": "success",
                "results": results_df.to_dict(),
            }
    
    except Exception as e:
        logger.error(f"DESeq2 analysis failed: {e}")
        return {
            "method": "DESeq2",
            "status": "failed",
            "error": str(e),
        }


def run_lefse(
    feature_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    subclass_column: Optional[str] = None,
) -> Dict[str, Any]:
    """Run LEfSe analysis via R (if available)."""
    if not R_AVAILABLE:
        return {
            "method": "LEfSe",
            "status": "unavailable",
            "message": "rpy2 is not installed. LEfSe requires R integration.",
        }
    
    return {
        "method": "LEfSe",
        "status": "placeholder",
        "message": "LEfSe implementation requires R package installation",
    }


def run_ancom(
    feature_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
) -> Dict[str, Any]:
    """Run ANCOM differential abundance analysis via R."""
    if not R_AVAILABLE:
        return {
            "method": "ANCOM",
            "status": "unavailable",
            "message": "rpy2 is not installed. ANCOM requires R integration.",
        }
    
    return {
        "method": "ANCOM",
        "status": "placeholder",
        "message": "ANCOM implementation requires R package installation",
    }


def run_maaslin2(
    feature_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    fixed_effects: List[str],
    random_effects: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Run MaAsLin2 multivariate association analysis via R."""
    if not R_AVAILABLE:
        return {
            "method": "MaAsLin2",
            "status": "unavailable",
            "message": "rpy2 is not installed. MaAsLin2 requires R integration.",
        }
    
    return {
        "method": "MaAsLin2",
        "status": "placeholder",
        "message": "MaAsLin2 implementation requires R package installation",
    }


def run_aldex2(
    feature_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
) -> Dict[str, Any]:
    """Run ALDEx2 differential abundance analysis via R."""
    if not R_AVAILABLE:
        return {
            "method": "ALDEx2",
            "status": "unavailable",
            "message": "rpy2 is not installed. ALDEx2 requires R integration.",
        }
    
    return {
        "method": "ALDEx2",
        "status": "placeholder",
        "message": "ALDEx2 implementation requires R package installation",
    }
