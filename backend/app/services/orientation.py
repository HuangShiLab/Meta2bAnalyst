"""Meta2bAnalyst - Feature-table orientation contract.

Every analysis in this codebase expects a feature table in **features x samples**
form (rows = taxa/metabolites/genes, columns = samples). Real-world uploads come
in both orientations, and previously each analysis function guessed on its own
with a different ad-hoc regex -- so alpha diversity could transpose a table while
PCoA did not, producing two mutually inconsistent results from one upload with
no error raised.

This module makes orientation a single, explicit decision:

1. If metadata is available, the orientation is *determined* by which axis of the
   feature table overlaps the metadata sample IDs. This is unambiguous for any
   dataset whose metadata actually describes its samples.
2. If no metadata is available, the documented convention (rows = features) is
   assumed and the result is flagged ``confidence="assumed"`` so callers can warn.
3. If the data contradicts both (no overlap, or an equally good match on both
   axes), an :class:`OrientationError` is raised instead of guessing. Callers map
   this to HTTP 400 -- a clear failure beats a plausible-looking wrong figure.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class OrientationError(ValueError):
    """Raised when a feature table's orientation cannot be established."""


@dataclass
class OrientationReport:
    """How a feature table's orientation was decided."""

    transposed: bool
    """True if the input had to be transposed to reach features x samples."""

    confidence: str
    """'determined' (matched against metadata) or 'assumed' (no metadata)."""

    n_features: int = 0
    n_samples: int = 0
    matched_samples: int = 0
    """Number of columns that matched a metadata sample ID (0 when assumed)."""

    warnings: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transposed": self.transposed,
            "confidence": self.confidence,
            "n_features": self.n_features,
            "n_samples": self.n_samples,
            "matched_samples": self.matched_samples,
            "warnings": list(self.warnings),
        }


def _overlap(labels: pd.Index, sample_ids: pd.Index) -> int:
    """Count labels that appear in sample_ids, comparing as strings."""
    left = {str(x).strip() for x in labels}
    right = {str(x).strip() for x in sample_ids}
    return len(left & right)


def resolve_feature_table(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    *,
    name: str = "feature table",
) -> Tuple[pd.DataFrame, OrientationReport]:
    """Return ``df`` in canonical features x samples orientation.

    Args:
        df: Feature table in either orientation.
        metadata_df: Optional metadata indexed by sample ID. When supplied it is
            the authority on which axis holds samples.
        name: Human-readable name used in error messages.

    Returns:
        ``(df_features_x_samples, report)``.

    Raises:
        OrientationError: If the table is empty, or metadata is supplied but
            neither axis matches it, or both axes match it equally well.
    """
    if df is None or df.empty:
        raise OrientationError(f"The {name} is empty.")

    if metadata_df is None or metadata_df.empty:
        report = OrientationReport(
            transposed=False,
            confidence="assumed",
            n_features=len(df.index),
            n_samples=len(df.columns),
            warnings=[
                f"No metadata available, so the {name} orientation was assumed to "
                f"follow the documented convention (rows = features, columns = "
                f"samples): {len(df.index)} features x {len(df.columns)} samples. "
                f"Upload a metadata file to have this verified."
            ],
        )
        return df, report

    sample_ids = metadata_df.index
    overlap_cols = _overlap(df.columns, sample_ids)   # already features x samples
    overlap_rows = _overlap(df.index, sample_ids)     # needs transposing

    if overlap_cols == 0 and overlap_rows == 0:
        raise OrientationError(
            f"None of the {name}'s row or column labels match any sample ID in the "
            f"metadata. Checked {len(df.index)} row labels (e.g. "
            f"{_preview(df.index)}) and {len(df.columns)} column labels (e.g. "
            f"{_preview(df.columns)}) against {len(sample_ids)} metadata sample IDs "
            f"(e.g. {_preview(sample_ids)}). Make sure the feature table and the "
            f"metadata use the same sample identifiers."
        )

    if overlap_cols == overlap_rows:
        raise OrientationError(
            f"Cannot determine the orientation of the {name}: rows and columns "
            f"match the metadata sample IDs equally well ({overlap_rows} each). "
            f"Please supply a table whose sample IDs appear on exactly one axis."
        )

    transposed = overlap_rows > overlap_cols
    out = df.T if transposed else df
    matched = max(overlap_rows, overlap_cols)

    report = OrientationReport(
        transposed=transposed,
        confidence="determined",
        n_features=len(out.index),
        n_samples=len(out.columns),
        matched_samples=matched,
    )

    if transposed:
        logger.info(
            "Transposed %s to features x samples (%d features x %d samples) based on "
            "metadata sample IDs.", name, len(out.index), len(out.columns)
        )

    unmatched = len(out.columns) - matched
    if unmatched > 0:
        report.warnings.append(
            f"{unmatched} of {len(out.columns)} samples in the {name} have no "
            f"metadata row and will be dropped by analyses that need grouping."
        )

    return out, report


def _preview(index: pd.Index, k: int = 3) -> str:
    """Render the first few labels for use in error messages."""
    return ", ".join(repr(str(x)) for x in list(index[:k])) or "<empty>"


def assert_sample_alignment(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame],
    group_column: Optional[str] = None,
    *,
    min_samples: int = 3,
    name: str = "feature table",
) -> pd.Index:
    """Check that a canonical feature table lines up with the metadata.

    Args:
        df: Feature table in features x samples orientation.
        metadata_df: Metadata indexed by sample ID.
        group_column: Optional grouping column that must exist and yield >=2
            non-empty groups among the shared samples.
        min_samples: Minimum number of shared samples required.
        name: Human-readable name used in error messages.

    Returns:
        The Index of samples present in both the feature table and the metadata.

    Raises:
        OrientationError: If the overlap is too small, the group column is
            missing, or fewer than two groups survive.
    """
    if metadata_df is None or metadata_df.empty:
        raise OrientationError(
            "This analysis needs a metadata file, but none has been uploaded for "
            "this session."
        )

    shared = df.columns.intersection(metadata_df.index)
    if len(shared) < min_samples:
        raise OrientationError(
            f"Only {len(shared)} sample(s) are present in both the {name} and the "
            f"metadata; at least {min_samples} are required. Feature-table samples "
            f"look like {_preview(df.columns)}; metadata sample IDs look like "
            f"{_preview(metadata_df.index)}."
        )

    if group_column is not None:
        if group_column not in metadata_df.columns:
            available = ", ".join(str(c) for c in metadata_df.columns[:10])
            raise OrientationError(
                f"Grouping column '{group_column}' is not in the metadata. "
                f"Available columns: {available}."
            )
        groups = metadata_df.loc[shared, group_column].dropna()
        n_groups = groups.nunique()
        if n_groups < 2:
            raise OrientationError(
                f"Grouping column '{group_column}' has {n_groups} distinct value(s) "
                f"across the {len(shared)} shared samples; at least 2 are needed to "
                f"compare groups."
            )

    return shared
