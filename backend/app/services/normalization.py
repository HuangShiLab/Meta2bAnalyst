"""
normalization.py  —  Meta2bAnalyst 统一标准化入口
====================================================
支持微生物组专用方法（TSS / CSS / CLR / ILR / TMM / Rarefaction）
和代谢组学方法（z-score / Pareto / Quantile / Sum / log1p）。

输入：features × samples DataFrame（与 Meta2bAnalyst 会话约定一致）
输出：标准化后矩阵 + 缩放因子 + Plotly 可视化
"""

import logging
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import quantile_transform

logger = logging.getLogger(__name__)


def run_normalization(
    df: pd.DataFrame,
    data_type: str = "microbiome",
    method: str = "clr",
    reference_samples: Optional[list] = None,
) -> Dict[str, Any]:
    """
    统一标准化入口。

    Parameters
    ----------
    df : pd.DataFrame
        features × samples 矩阵
    data_type : str
        "microbiome" | "metabolome"
    method : str
        微生物组: "tss", "css", "clr", "ilr", "tmm", "rarefaction", "none"
        代谢组学: "zscore", "pareto", "quantile", "sum", "log1p", "none"
    reference_samples : list | None
        用于计算参考分布的样本子集（列名列表）

    Returns
    -------
    dict:
        normalized_matrix : pd.DataFrame
        scaling_factors   : dict
        plot_data         : dict (Plotly JSON)
    """
    if df.empty:
        raise ValueError("Input data frame is empty.")

    # 确保非负（微生物组）
    if data_type == "microbiome" and (df < 0).any().any():
        raise ValueError("Microbiome data must be non-negative.")

    # 转置为 samples × features 方便按样本操作，最后转回来
    X = df.T.copy()  # samples × features
    n_samples, n_features = X.shape
    scaling_factors: Dict[str, Any] = {"method": method, "data_type": data_type}

    if method == "none":
        X_norm = X.copy()

    # ── Microbiome methods ──────────────────────────────────────────
    elif method == "tss":
        # Total Sum Scaling: divide each sample by its total count
        col_sums = X.sum(axis=1)
        X_norm = X.div(col_sums, axis=0)
        scaling_factors["sample_totals"] = col_sums.to_dict()

    elif method == "css":
        # Cumulative Sum Scaling (metagenomeSeq-style)
        X_norm, scaling_factors = _css_normalize(X, scaling_factors)

    elif method == "clr":
        # Centered Log Ratio: log(x/gmean) per sample
        # Add small pseudo-count to zeros
        X_pseudo = X.replace(0, np.nan)
        min_nonzero = X_pseudo.min().min()
        pseudo = min_nonzero * 0.5 if pd.notna(min_nonzero) and min_nonzero > 0 else 1e-6
        X_filled = X.replace(0, pseudo)
        log_x = np.log(X_filled)
        gmean = log_x.mean(axis=1)
        X_norm = log_x.sub(gmean, axis=0)
        scaling_factors["pseudo_count"] = pseudo
        scaling_factors["geometric_mean"] = np.exp(gmean).to_dict()

    elif method == "ilr":
        # Isometric Log Ratio: sequential binary partition balances
        X_norm = _ilr_transform(X)
        scaling_factors["note"] = "ILR balances (not directly reversible)"

    elif method == "tmm":
        # Trimmed Mean of M-values (edgeR-style simplified)
        X_norm, scaling_factors = _tmm_normalize(X, scaling_factors)

    elif method == "rarefaction":
        # Rarefaction to minimum library size
        lib_sizes = X.sum(axis=1)
        min_depth = int(lib_sizes.min())
        X_norm = _rarefy(X, min_depth)
        scaling_factors["rarefaction_depth"] = min_depth
        scaling_factors["original_lib_sizes"] = lib_sizes.to_dict()

    # ── Metabolome methods ──────────────────────────────────────────
    elif method == "zscore":
        # (x - mean) / std  per feature
        means = X.mean(axis=0)
        stds = X.std(axis=0, ddof=1).replace(0, 1)
        X_norm = (X - means) / stds
        scaling_factors["feature_means"] = means.to_dict()
        scaling_factors["feature_stds"] = stds.to_dict()

    elif method == "pareto":
        # Divide by sqrt(std) per feature
        stds = X.std(axis=0, ddof=1).replace(0, 1)
        X_norm = X / np.sqrt(stds)
        scaling_factors["feature_sqrt_stds"] = np.sqrt(stds).to_dict()

    elif method == "quantile":
        # Quantile normalization (samples to average distribution)
        X_arr = quantile_transform(X.values, axis=0, n_quantiles=min(n_samples, 1000), random_state=42)
        X_norm = pd.DataFrame(X_arr, index=X.index, columns=X.columns)
        scaling_factors["n_quantiles"] = min(n_samples, 1000)

    elif method == "sum":
        # Divide each sample by its sum
        col_sums = X.sum(axis=1)
        X_norm = X.div(col_sums, axis=0)
        scaling_factors["sample_totals"] = col_sums.to_dict()

    elif method == "log1p":
        # log(1 + x)
        X_norm = np.log1p(X)
        scaling_factors["transformation"] = "log1p"

    else:
        raise ValueError(f"Unknown normalization method: {method}")

    # 转回 features × samples
    result_df = X_norm.T

    # 可视化：标准化前后样本总和/分布箱线图
    plot_data = _normalization_plot(df, result_df, method)

    return {
        "normalized_matrix": result_df,
        "scaling_factors": scaling_factors,
        "plot_data": plot_data,
    }


# ── 辅助函数 ──────────────────────────────────────────────────────

def _css_normalize(X: pd.DataFrame, sf: Dict) -> tuple:
    """
    Cumulative Sum Scaling (Paulson et al., 2013).
    Simplified implementation: use the 75th percentile as the reference quantile.
    """
    # 计算每个样本的非零值分位数
    quantiles = []
    for idx in X.index:
        vals = X.loc[idx]
        nonzeros = vals[vals > 0]
        if len(nonzeros) == 0:
            quantiles.append(0)
        else:
            quantiles.append(nonzeros.quantile(0.75))
    quantiles = pd.Series(quantiles, index=X.index)

    # 缩放因子 = 分位数的中位数 / 每个样本的分位数
    ref = quantiles.median()
    scale_factors = ref / quantiles.replace(0, np.nan)
    scale_factors = scale_factors.fillna(1.0)

    X_norm = X.mul(scale_factors, axis=0)
    sf["css_scale_factors"] = scale_factors.to_dict()
    sf["css_reference_quantile"] = ref
    return X_norm, sf


def _tmm_normalize(X: pd.DataFrame, sf: Dict) -> tuple:
    """
    Simplified TMM (Trimmed Mean of M-values).
    Reference: edgeR::calcNormFactors (Robinson & Oshlack, 2010).
    """
    # 选择参考样本（中位 lib size 最接近中位数的样本）
    lib_sizes = X.sum(axis=1)
    ref_idx = (lib_sizes - lib_sizes.median()).abs().idxmin()
    ref_sample = X.loc[ref_idx]
    ref_lib = lib_sizes.loc[ref_idx]

    scale_factors = {}
    for idx in X.index:
        if idx == ref_idx:
            scale_factors[idx] = 1.0
            continue
        # M = log2(x/ref) per feature, A = 0.5*log2(x*ref)
        x = X.loc[idx]
        # 过滤低表达特征
        mask = (x > 0) & (ref_sample > 0)
        if mask.sum() < 10:
            scale_factors[idx] = 1.0
            continue
        x_f = x[mask]
        r_f = ref_sample[mask]
        M = np.log2(x_f / r_f)
        A = 0.5 * np.log2(x_f * r_f)
        # Trim 30% from M and 5% from A
        m_low, m_high = np.percentile(M, [30, 70])
        a_low, a_high = np.percentile(A, [5, 95])
        trim_mask = (M >= m_low) & (M <= m_high) & (A >= a_low) & (A <= a_high)
        if trim_mask.sum() < 5:
            scale_factors[idx] = 1.0
            continue
        tmm = 2 ** M[trim_mask].mean()
        # 调整为库大小
        scale_factors[idx] = tmm

    scale_series = pd.Series(scale_factors)
    # 几何均值归一化缩放因子
    gm = np.exp(np.log(scale_series.replace(0, np.nan)).mean())
    scale_series = scale_series / gm

    X_norm = X.div(scale_series, axis=0)
    sf["tmm_scale_factors"] = scale_series.to_dict()
    sf["tmm_reference_sample"] = ref_idx
    return X_norm, sf


def _rarefy(X: pd.DataFrame, depth: int) -> pd.DataFrame:
    """
    Rarefaction: random subsample each row to `depth` counts.
    """
    np.random.seed(42)
    result = X.copy()
    for idx in X.index:
        row = X.loc[idx]
        total = int(row.sum())
        if total <= depth:
            continue
        # Multinomial subsampling
        probs = row.values / total
        subsampled = np.random.multinomial(depth, probs)
        result.loc[idx] = subsampled
    return result


def _ilr_transform(X: pd.DataFrame) -> pd.DataFrame:
    """
    Simplified ILR: compute sequential binary partition balances.
    For a general implementation this requires a phylogenetic tree;
    here we use a simple sequential balance.
    """
    # CLR first
    X_pseudo = X.replace(0, X[X > 0].min().min() * 0.5)
    log_x = np.log(X_pseudo)
    gmean = log_x.mean(axis=1)
    clr = log_x.sub(gmean, axis=0)

    # Sequential balances: split features into two groups iteratively
    n_feat = clr.shape[1]
    balances = []
    balance_names = []
    features = list(clr.columns)

    for i in range(n_feat - 1):
        # Simple split: first i+1 vs rest
        left = features[: i + 1]
        right = features[i + 1 :]
        if len(right) == 0:
            break
        left_sum = clr[left].sum(axis=1) / len(left)
        right_sum = clr[right].sum(axis=1) / len(right)
        balance = np.sqrt((len(left) * len(right)) / (len(left) + len(right))) * (left_sum - right_sum)
        balances.append(balance)
        balance_names.append(f"balance_{i+1}")

    return pd.DataFrame(np.array(balances).T, index=clr.index, columns=balance_names)


def _normalization_plot(original: pd.DataFrame, normalized: pd.DataFrame, method: str) -> Dict[str, Any]:
    """
    生成标准化前后对比的 Plotly 箱线图。
    """
    # 样本总和对比
    orig_sums = original.sum(axis=0)
    norm_sums = normalized.sum(axis=0)

    fig = {
        "data": [
            {
                "type": "box",
                "name": "Before",
                "y": orig_sums.values.tolist(),
                "boxpoints": "all",
                "jitter": 0.3,
            },
            {
                "type": "box",
                "name": "After",
                "y": norm_sums.values.tolist(),
                "boxpoints": "all",
                "jitter": 0.3,
            },
        ],
        "layout": {
            "title": f"Sample totals: before vs after {method.upper()} normalization",
            "yaxis": {"title": "Sum"},
            "xaxis": {"title": ""},
        },
    }

    # 如果标准化后范围差异很大，加 log 轴选项
    if norm_sums.max() / max(norm_sums.min(), 1e-10) > 1000:
        fig["layout"]["yaxis"]["type"] = "log"

    return fig
