"""Small shared helpers for reading user-uploaded tabular files."""
import pandas as pd


def normalize_sample_index(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a sample-indexed frame's index to stripped strings.

    Purely numeric sample IDs (1007, 1010, ...) get parsed as int64 by the
    metadata reader while feature-table column labels stay strings, so every
    ``index.intersection(columns)`` came back empty -- alpha diversity
    silently lost its group statistics and box plots, and PERMANOVA failed
    with a misleading "table is probably transposed" error. Integral floats
    are cast through int first so IDs don't render as "1007.0".
    """
    idx = df.index
    if str(idx.dtype).startswith("float"):
        try:
            if (idx == idx.astype("int64")).all():
                idx = idx.astype("int64")
        except (ValueError, TypeError):
            pass
    df.index = idx.astype(str).str.strip()
    return df


def read_delimited(path, **kwargs) -> pd.DataFrame:
    """Read a TSV *or* CSV keeping every column (delimiter sniffed).

    Same rationale as read_indexed_table, for tables whose first column is
    data (e.g. strain tables: sample_id, species, strain, abundance) rather
    than an index.
    """
    try:
        return pd.read_csv(path, sep=None, engine="python", **kwargs)
    except Exception:
        pass
    try:
        return pd.read_csv(path, sep="\t", **kwargs)
    except Exception:
        return pd.read_csv(path, **kwargs)


def read_indexed_table(path, index_col: int = 0) -> pd.DataFrame:
    """Read a TSV *or* CSV into a DataFrame indexed by its first column.

    Uploads accept both delimiters, so the historical "try tab, fall back to
    comma" dance is not enough: ``pd.read_csv(sep='\\t')`` on a comma file
    does NOT raise — it silently returns whole lines as the index, which
    zeroed out every sample-ID match downstream. Sniffing the delimiter
    (``sep=None, engine='python'``) reads both correctly; single-column files
    where the sniffer gives up fall back to tab, then comma.
    """
    try:
        return normalize_sample_index(pd.read_csv(path, sep=None, engine="python", index_col=index_col))
    except Exception:
        pass
    try:
        return normalize_sample_index(pd.read_csv(path, sep="\t", index_col=index_col))
    except Exception:
        return normalize_sample_index(pd.read_csv(path, index_col=index_col))
