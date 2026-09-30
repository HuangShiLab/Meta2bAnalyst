"""Meta2bAnalyst - study-design detection shared by statistics and the planner.

Repeated samples from the same participant are not independent. Tests that
permute samples freely (PERMANOVA, Mantel) or treat every sample as a unit
(one-way ANOVA) then overstate significance for factors that vary between
participants -- the classic pseudo-replication problem (Hurlbert 1984). This
module finds the column that identifies the participant so that callers can
restrict permutations or warn.

Detection is deliberately conservative: a column is only proposed when its
*name* says it identifies a subject (subject, host, participant, patient, ...)
AND its values repeat across samples. Columns such as ``Visit`` or ``Group``
also repeat, so repetition alone is never enough.
"""
import re
from typing import Optional

import pandas as pd

_SUBJECT_NAME = re.compile(
    r"(subject|participant|patient|host|individual|donor|person|volunteer|"
    r"child|animal|mouse|mice|^pid$|^sid$|_id$|^id$)",
    re.IGNORECASE,
)
_TIME_NAME = re.compile(r"(time|visit|day|week|month|timepoint|date|session)", re.IGNORECASE)


def detect_subject_column(metadata_df: Optional[pd.DataFrame], exclude: Optional[str] = None) -> Optional[str]:
    """Return the metadata column that identifies participants, or None.

    A candidate must (1) have a subject-like name, (2) have at least 2 levels,
    and (3) repeat: on average >= 1.5 samples per level, with most samples
    belonging to a level that occurs more than once.
    """
    if metadata_df is None or metadata_df.empty:
        return None
    n = len(metadata_df)
    best, best_levels = None, None
    for col in metadata_df.columns:
        if col == exclude or not _SUBJECT_NAME.search(str(col)):
            continue
        values = metadata_df[col].dropna()
        if values.empty:
            continue
        counts = values.value_counts()
        n_levels = len(counts)
        if n_levels < 2 or n / n_levels < 1.5:
            continue
        if counts[counts > 1].sum() / len(values) < 0.8:
            continue
        # Prefer the most specific identifier (most levels) when several match.
        if best is None or n_levels > best_levels:
            best, best_levels = col, n_levels
    return best


def detect_time_column(metadata_df: Optional[pd.DataFrame], subject_column: Optional[str] = None) -> Optional[str]:
    """Return a column that indexes repeated visits within subjects, or None."""
    if metadata_df is None or metadata_df.empty or subject_column is None:
        return None
    for col in metadata_df.columns:
        if col == subject_column or not _TIME_NAME.search(str(col)):
            continue
        per_subject = metadata_df.groupby(subject_column)[col].nunique()
        if len(per_subject) and (per_subject > 1).mean() >= 0.5:
            return col
    return None


def factor_level(metadata_df: pd.DataFrame, factor: str, subject_column: str) -> str:
    """Classify ``factor`` relative to ``subject_column``.

    Returns 'between_subject' when every subject carries a single level (e.g.
    case/control), 'within_subject' otherwise (e.g. visit).
    """
    levels = metadata_df.groupby(subject_column)[factor].nunique(dropna=True)
    return "between_subject" if (levels <= 1).all() else "within_subject"
