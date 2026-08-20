"""
outlier_detection.py  —  Meta2bAnalyst 离群值检测模块
========================================================
支持四种策略：
  1. Aitchison 距离（CLR → 欧氏距离）
  2. PCA 马氏距离
  3. 孤立森林（Isolation Forest）
  4. Cook 距离

输入：features × samples DataFrame + 可选 metadata
输出：离群标记 + 诊断可视化
"""

import logging
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import mahalanobis
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.covariance import MinCovDet

logger = logging.getLogger(__name__)


def run_outlier_detection(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    method: str = "aitchison",
    group_column: Optional[str] = None,
    threshold: float = 0.05,
) -> Dict[str, Any]:
    """
    多策略离群值检测。

    Parameters
    ----------
    df : pd.DataFrame
        features × samples 矩阵
    metadata_df : pd.DataFrame | None
        样本注释表（samples × variables）
    method : str
        "aitchison" | "mahalanobis_pca" | "isolation_forest" | "cooks_distance"
    group_column : str | None
        分组变量（用于组内独立检测）
    threshold : float
        显著性阈值（α），默认 0.05

    Returns
    -------
    dict:
        outlier_flags : pd.DataFrame  (sample_id, score, is_outlier, method)
        plot_data     : dict (Plotly JSON)
        report        : dict (检出摘要)
    """
    if df.empty:
        raise ValueError("Input data frame is empty.")

    samples = df.columns.tolist()

    # 如果有 group_column，按组拆分检测
    if group_column and metadata_df is not None and group_column in metadata_df.columns:
        groups = metadata_df[group_column].unique()
        all_flags = []
        for g in groups:
            group_samples = metadata_df[metadata_df[group_column] == g].index.intersection(df.columns)
            if len(group_samples) < 3:
                continue
            group_df = df[group_samples]
            flags = _detect_outliers_single(
                group_df, method=method, threshold=threshold, label_prefix=f"{group_column}={g}"
            )
            all_flags.append(flags)
        outlier_df = pd.concat(all_flags, ignore_index=True) if all_flags else pd.DataFrame()
    else:
        outlier_df = _detect_outliers_single(df, method=method, threshold=threshold)

    # 可视化
    plot_data = _outlier_plot(df, outlier_df, metadata_df, group_column)

    # 报告
    report = {
        "method": method,
        "threshold": threshold,
        "n_samples": len(samples),
        "n_outliers": int(outlier_df["is_outlier"].sum()) if not outlier_df.empty else 0,
        "outlier_rate": float(outlier_df["is_outlier"].mean()) if not outlier_df.empty else 0.0,
        "outlier_samples": outlier_df.loc[outlier_df["is_outlier"], "sample_id"].tolist() if not outlier_df.empty else [],
    }

    return {
        "outlier_flags": outlier_df,
        "plot_data": plot_data,
        "report": report,
    }


def _detect_outliers_single(
    df: pd.DataFrame, method: str, threshold: float, label_prefix: str = ""
) -> pd.DataFrame:
    """对单个数据块执行离群检测。"""
    samples = df.columns.tolist()
    n_samples = len(samples)

    if method == "aitchison":
        # CLR 转换 → 欧氏距离 → χ² 分位数判定
        X = df.T.copy()  # samples × features
        # 伪计数
        X_pos = X.replace(0, np.nan)
        min_nz = X_pos.min().min()
        pseudo = min_nz * 0.5 if pd.notna(min_nz) and min_nz > 0 else 1e-6
        X_filled = X.replace(0, pseudo)
        log_x = np.log(X_filled)
        gmean = log_x.mean(axis=1)
        clr = log_x.sub(gmean, axis=0).values  # (n_samples, n_features)

        # 到 CLR 空间中心的欧氏距离
        center = clr.mean(axis=0)
        dists = np.sqrt(((clr - center) ** 2).sum(axis=1))

        # 阈值：χ² 分布的 (1-α) 分位数，自由度 = n_features
        # 但特征维度通常 >> 样本数，改用 IQR 方法
        q1, q3 = np.percentile(dists, [25, 75])
        iqr = q3 - q1
        cutoff = q3 + 1.5 * iqr
        flags = dists > cutoff
        scores = dists

    elif method == "mahalanobis_pca":
        # PCA 降维 → 马氏距离
        X = df.T.values
        n_comp = min(10, X.shape[0] - 1, X.shape[1])
        if n_comp < 2:
            # 样本太少，回退到 Aitchison
            return _detect_outliers_single(df, "aitchison", threshold, label_prefix)

        pca = PCA(n_components=n_comp)
        coords = pca.fit_transform(X)  # (n_samples, n_comp)

        # 稳健协方差估计（MinCovDet）
        try:
            mcd = MinCovDet(random_state=42).fit(coords)
            cov_inv = np.linalg.inv(mcd.covariance_)
            center = mcd.location_
        except Exception:
            # 回退到标准估计
            cov = np.cov(coords.T)
            cov_inv = np.linalg.pinv(cov)
            center = coords.mean(axis=0)

        dists = np.array([mahalanobis(coords[i], center, cov_inv) for i in range(n_samples)])

        # 卡方分布阈值
        cutoff = np.sqrt(stats.chi2.ppf(1 - threshold, df=n_comp))
        flags = dists > cutoff
        scores = dists

    elif method == "isolation_forest":
        # 孤立森林（基于特征空间，非距离）
        X = df.T.values
        # 过滤全零特征
        nonzero_var = X.var(axis=0) > 0
        if nonzero_var.sum() == 0:
            flags = np.zeros(n_samples, dtype=bool)
            scores = np.zeros(n_samples)
        else:
            X_f = X[:, nonzero_var]
            clf = IsolationForest(contamination=threshold, random_state=42)
            preds = clf.fit_predict(X_f)  # 1 = inlier, -1 = outlier
            raw_scores = clf.decision_function(X_f)  # 越高越正常
            flags = preds == -1
            scores = -raw_scores  # 反转：越高越异常

    elif method == "cooks_distance":
        # 基于主成分得分的简化 Cook 距离
        X = df.T.values
        n_comp = min(5, X.shape[0] - 1, X.shape[1])
        if n_comp < 2:
            return _detect_outliers_single(df, "aitchison", threshold, label_prefix)

        pca = PCA(n_components=n_comp)
        coords = pca.fit_transform(X)
        # 对每个 PC 拟合简单模型 y = PC，计算 Cook 距离
        cook_scores = np.zeros(n_samples)
        for d in range(n_comp):
            y = coords[:, d]
            X_design = np.ones((n_samples, 1))
            # OLS
            beta = np.linalg.lstsq(X_design, y, rcond=None)[0]
            y_hat = X_design @ beta
            residuals = y - y_hat
            mse = np.mean(residuals ** 2)
            if mse == 0:
                continue
            h = 1.0 / n_samples  # 简化 leverage
            cooks_d = (residuals ** 2 / (mse * (1 + 1))) * (h / (1 - h) ** 2)
            cook_scores += cooks_d

        # F 分布阈值
        cutoff = stats.f.ppf(1 - threshold, dfn=n_comp, dfd=n_samples - n_comp)
        flags = cook_scores > cutoff
        scores = cook_scores

    else:
        raise ValueError(f"Unknown outlier detection method: {method}")

    return pd.DataFrame({
        "sample_id": samples,
        "score": scores,
        "is_outlier": flags,
        "method": method,
        "group": label_prefix if label_prefix else "all",
    })


def _outlier_plot(
    df: pd.DataFrame,
    outlier_df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame],
    group_column: Optional[str],
) -> Dict[str, Any]:
    """生成 PCA 散点图，离群样本红色标注。"""
    X = df.T.values
    n_comp = min(2, X.shape[0] - 1, X.shape[1])
    if n_comp < 2:
        return {"data": [], "layout": {"title": "Not enough dimensions for PCA plot"}}

    pca = PCA(n_components=n_comp)
    coords = pca.fit_transform(X)

    sample_ids = df.columns.tolist()
    outlier_set = set(outlier_df.loc[outlier_df["is_outlier"], "sample_id"])

    # 分组颜色
    if group_column and metadata_df is not None and group_column in metadata_df.columns:
        groups = metadata_df.loc[sample_ids, group_column]
        unique_groups = groups.unique()
        traces = []
        for g in unique_groups:
            mask = groups == g
            g_samples = [s for s, m in zip(sample_ids, mask) if m]
            g_coords = coords[mask]
            g_outliers = [s in outlier_set for s in g_samples]
            traces.append({
                "type": "scatter",
                "mode": "markers",
                "name": str(g),
                "x": g_coords[:, 0].tolist(),
                "y": g_coords[:, 1].tolist(),
                "marker": {
                    "size": [12 if o else 8 for o in g_outliers],
                    "color": ["red" if o else "blue" for o in g_outliers],
                    "opacity": 0.7,
                },
                "text": g_samples,
            })
    else:
        colors = ["red" if s in outlier_set else "blue" for s in sample_ids]
        sizes = [12 if s in outlier_set else 8 for s in sample_ids]
        traces = [{
            "type": "scatter",
            "mode": "markers",
            "name": "samples",
            "x": coords[:, 0].tolist(),
            "y": coords[:, 1].tolist(),
            "marker": {"size": sizes, "color": colors, "opacity": 0.7},
            "text": sample_ids,
        }]

    return {
        "data": traces,
        "layout": {
            "title": "Outlier Detection (PCA view)",
            "xaxis": {"title": f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)"},
            "yaxis": {"title": f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)"},
        },
    }
