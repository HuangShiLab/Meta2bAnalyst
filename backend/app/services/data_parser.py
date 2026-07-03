"""
Meta2bAnalyst - Data Parser Service
Handles parsing of TSV/CSV, BIOM, Mothur, 2bRAD, and Strain2bScan formats.
"""
import logging
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def detect_file_format(file_path: Path) -> str:
    """Detect file format based on extension and content."""
    ext = file_path.suffix.lower()
    
    if ext == ".biom":
        return "biom"
    elif ext in (".shared",):
        return "mothur_shared"
    elif ext in (".taxonomy",):
        return "mothur_taxonomy"
    elif ext in (".csv",):
        return "csv"
    elif ext in (".tsv", ".txt"):
        # Check if it's a 2bRAD or Strain2bScan file by reading first line
        with open(file_path, "r") as f:
            first_line = f.readline().strip()
        if "strain" in first_line.lower() or "ani" in first_line.lower():
            return "strain"
        if "tag" in first_line.lower():
            return "tag2bmap"
        return "tsv"
    elif ext in (".h5", ".hdf5"):
        return "biom_hdf5"
    else:
        return "unknown"


def parse_tsv_csv(file_path: Path, sep: str = "\t", index_col: int = 0, comment: str = "#") -> pd.DataFrame:
    """Parse TSV or CSV file into a pandas DataFrame."""
    try:
        # Try to detect if first row is header
        df = pd.read_csv(
            file_path,
            sep=sep,
            index_col=index_col,
            comment=comment,
            engine="python",
        )
        # Ensure numeric data
        df = df.apply(pd.to_numeric, errors="coerce")
        # Drop rows/columns that are all NaN
        df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)
        return df
    except Exception as e:
        logger.error(f"Failed to parse TSV/CSV file {file_path}: {e}")
        raise


def parse_biom_file(file_path: Path) -> pd.DataFrame:
    """Parse BIOM format file into a pandas DataFrame."""
    try:
        import biom
        table = biom.load_table(str(file_path))
        df = pd.DataFrame(
            table.matrix_data.toarray().T,
            index=table.ids(axis="sample"),
            columns=table.ids(axis="observation"),
        ).T  # Transpose to features x samples
        return df
    except ImportError:
        logger.warning("biom-format not installed, falling back to JSON parsing")
        import json
        with open(file_path, "r") as f:
            biom_data = json.load(f)
        # Extract matrix data from BIOM JSON
        matrix_type = biom_data.get("matrix_type", "dense")
        data = biom_data.get("data", [])
        rows = biom_data.get("rows", [])
        columns = biom_data.get("columns", [])
        
        observation_ids = [r["id"] for r in rows]
        sample_ids = [c["id"] for c in columns]
        
        if matrix_type == "dense":
            df = pd.DataFrame(data, index=observation_ids, columns=sample_ids)
        else:  # sparse
            # Convert sparse matrix to dense
            matrix = [[0] * len(sample_ids) for _ in range(len(observation_ids))]
            for row_idx, col_idx, value in data:
                matrix[row_idx][col_idx] = value
            df = pd.DataFrame(matrix, index=observation_ids, columns=sample_ids)
        
        return df
    except Exception as e:
        logger.error(f"Failed to parse BIOM file {file_path}: {e}")
        raise


def parse_mothur_shared(file_path: Path) -> pd.DataFrame:
    """Parse Mothur .shared file into a pandas DataFrame."""
    try:
        # Mothur shared format: label	group	numOtus	OTU1	OTU2...
        df = pd.read_csv(file_path, sep="\t", index_col=1)
        # Drop label and numOtus columns, keep only OTU columns
        if "label" in df.columns:
            df = df.drop(columns=["label"])
        if "numOtus" in df.columns:
            df = df.drop(columns=["numOtus"])
        return df
    except Exception as e:
        logger.error(f"Failed to parse Mothur shared file {file_path}: {e}")
        raise


def parse_mothur_taxonomy(file_path: Path) -> pd.DataFrame:
    """Parse Mothur .taxonomy file into a pandas DataFrame."""
    try:
        # Mothur taxonomy: OTU\ttaxonomy	size
        df = pd.read_csv(
            file_path,
            sep="\t",
            names=["OTU", "taxonomy", "size"],
            index_col=0,
        )
        return df
    except Exception as e:
        logger.error(f"Failed to parse Mothur taxonomy file {file_path}: {e}")
        raise


def parse_2brad_file(file_path: Path) -> pd.DataFrame:
    """Parse 2bRAD-M species abundance table."""
    try:
        df = pd.read_csv(file_path, sep="\t", index_col=0)
        df = df.apply(pd.to_numeric, errors="coerce")
        df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)
        return df
    except Exception as e:
        logger.error(f"Failed to parse 2bRAD file {file_path}: {e}")
        raise


def parse_strain2bscan(file_path: Path) -> pd.DataFrame:
    """Parse Strain2bScan output file."""
    try:
        df = pd.read_csv(file_path, sep="\t", index_col=0)
        return df
    except Exception as e:
        logger.error(f"Failed to parse Strain2bScan file {file_path}: {e}")
        raise


def parse_tag2bmap(file_path: Path) -> pd.DataFrame:
    """Parse Tag2bMap output file."""
    try:
        df = pd.read_csv(file_path, sep="\t", index_col=0)
        return df
    except Exception as e:
        logger.error(f"Failed to parse Tag2bMap file {file_path}: {e}")
        raise


def parse_data_file(
    file_path: Path,
    file_type: Optional[str] = None,
) -> Tuple[pd.DataFrame, str]:
    """
    Parse a data file and return a pandas DataFrame.

    Args:
        file_path: Path to the data file
        file_type: Optional explicit file type hint

    Returns:
        Tuple of (DataFrame, detected_format)
    """
    detected_format = file_type or detect_file_format(file_path)
    logger.info(f"Parsing file {file_path} as format: {detected_format}")
    
    if detected_format in ("tsv", "txt"):
        df = parse_tsv_csv(file_path, sep="\t")
    elif detected_format == "csv":
        df = parse_tsv_csv(file_path, sep=",")
    elif detected_format == "biom":
        df = parse_biom_file(file_path)
    elif detected_format == "mothur_shared":
        df = parse_mothur_shared(file_path)
    elif detected_format == "mothur_taxonomy":
        df = parse_mothur_taxonomy(file_path)
    elif detected_format == "strain":
        df = parse_strain2bscan(file_path)
    elif detected_format == "tag2bmap":
        df = parse_tag2bmap(file_path)
    elif detected_format == "2brad":
        df = parse_2brad_file(file_path)
    else:
        # Fallback: try as TSV
        logger.warning(f"Unknown format '{detected_format}', attempting TSV parse")
        df = parse_tsv_csv(file_path, sep="\t")
    
    logger.info(f"Parsed {file_path}: shape={df.shape}, features={len(df.index)}, samples={len(df.columns)}")
    return df, detected_format
