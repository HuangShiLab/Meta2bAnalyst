"""Small shared helpers for reading user-uploaded tabular files."""
import pandas as pd


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
        return pd.read_csv(path, sep=None, engine="python", index_col=index_col)
    except Exception:
        pass
    try:
        return pd.read_csv(path, sep="\t", index_col=index_col)
    except Exception:
        return pd.read_csv(path, index_col=index_col)
