"""
Cross-Site / Cross-Omics Statistics
====================================
Implements the statistical framework of Zhang et al. (Microbiome 2026,
doi:10.1186/s40168-026-02405-w, "Cross-body site microbial interactions
influence the human plasma metabolome") as reusable platform services:

1. ``cross_site_explained_variance`` -- distance-based variance estimation:
   per-feature univariate PERMANOVA of each site's features against an
   omics-B (e.g. metabolome) distance matrix, then a cumulative
   multivariable model over the significant features (adonis2-style
   sequential sums of squares). Answers "how much of omics-B does each
   body site explain?".

2. ``cross_omics_gbdt_screen`` -- per-target gradient-boosting models with
   nested cross-validation, in-fold Spearman feature pre-selection
   (|r| >= threshold, p < 0.05), bootstrap R2 distribution with 95% CI,
   one-sample t-test vs 0, and feature reproducibility. Answers "which
   features carry the cross-omics association?". Falls back to LASSO with
   a permutation null when ``method="lasso"``.

3. ``cross_site_correlation_network`` -- Spearman feature-x-target
   correlation network per site (|r| >= threshold, p < threshold), FDR,
   network centralities, per-site hubs, and targets shared across sites.

4. ``cross_site_concordance`` -- for a metadata variable (e.g. disease
   group), tests each feature per site/omics and reports features that
   are significant (FDR) in >= ``min_sites`` sites with the SAME direction
   of effect. Answers "which cross-site features are disease-associated,
   concordantly?".

All frames are samples x features unless stated otherwise.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────
# 1. Distance-based variance estimation (adonis2-style)
# ───────────────────────────────────────────────────────────────

def _gower_center(dist: np.ndarray) -> np.ndarray:
    """Gower-centered matrix of a squared-distance matrix."""
    n = dist.shape[0]
    d2 = dist ** 2
    H = np.eye(n) - np.ones((n, n)) / n
    return -0.5 * H @ d2 @ H


def _hat_matrix(X: np.ndarray) -> np.ndarray:
    """Projection (hat) matrix for design matrix X with intercept."""
    X1 = np.column_stack([np.ones(len(X)), X])
    # pinv guards against collinearity among genera
    return X1 @ np.linalg.pinv(X1.T @ X1) @ X1.T


def db_permanova(
    X: pd.DataFrame,
    dist: np.ndarray,
    n_perm: int = 999,
    seed: int = 42,
) -> Dict[str, Any]:
    """Distance-based linear model (adonis2 with sequential terms).

    Parameters
    ----------
    X : samples x predictors (continuous or dummy-coded).
    dist : n x n distance matrix of the response (e.g. metabolome Euclidean).

    Returns per-term sequential R2 / pseudo-F / p (permutation), plus the
    cumulative R2 of the full model.
    """
    rng = np.random.default_rng(seed)
    G = _gower_center(np.asarray(dist, dtype=float))
    n = G.shape[0]
    ss_total = float(np.trace(G))

    Xv = X.apply(stats.zscore) if X.shape[1] else X
    Xv = np.nan_to_num(np.asarray(Xv, dtype=float))

    terms: List[Dict[str, Any]] = []
    fitted = np.zeros((n, n))  # cumulative hat contribution
    prev_rank = 1  # intercept

    H_cum = np.ones((n, n)) / n  # intercept-only hat
    for col in (X.columns if X.shape[1] else []):
        H_new = _hat_matrix(Xv[:, : len(terms) + 1])
        ss_term = float(np.trace((H_new - H_cum) @ G))
        df_term = 1
        ss_res = float(np.trace((np.eye(n) - H_new) @ G))
        df_res = n - (len(terms) + 2)
        pseudo_f = (ss_term / df_term) / (ss_res / df_res) if ss_res > 0 else np.nan

        # Permutation test on the raw predictor values (adonis2 default)
        count = 1
        for _ in range(n_perm):
            idx = rng.permutation(n)
            Xp = Xv.copy()
            Xp[:, len(terms)] = Xv[idx, len(terms)]
            Hp = _hat_matrix(Xp[:, : len(terms) + 1])
            ss_p = float(np.trace((Hp - H_cum) @ G))
            ss_rp = float(np.trace((np.eye(n) - Hp) @ G))
            f_p = (ss_p / df_term) / (ss_rp / df_res) if ss_rp > 0 else 0.0
            if f_p >= pseudo_f:
                count += 1

        terms.append({
            "term": str(col),
            "r2": ss_term / ss_total if ss_total > 0 else np.nan,
            "pseudo_f": pseudo_f,
            "pvalue": count / (n_perm + 1),
        })
        H_cum = H_new
        prev_rank += 1

    H_full = _hat_matrix(Xv) if X.shape[1] else np.ones((n, n)) / n
    r2_cum = float(np.trace(H_full @ G) - np.trace(G) / n) / ss_total if ss_total > 0 else np.nan
    return {
        "terms": terms,
        "cumulative_r2": max(0.0, r2_cum) if not np.isnan(r2_cum) else np.nan,
        "n_samples": n,
        "n_permutations": n_perm,
    }


def cross_site_explained_variance(
    site_tables: Dict[str, pd.DataFrame],
    target_df: pd.DataFrame,
    p_threshold: float = 0.05,
    n_perm: int = 999,
    seed: int = 42,
    max_features_per_site: Optional[int] = None,
) -> Dict[str, Any]:
    """Per-site: how much of the target omics (e.g. plasma metabolome)
    does the site's feature table explain?

    Paper procedure: univariate PERMANOVA per feature; features with
    p < threshold enter a cumulative multivariable model whose R2 is the
    site's explanatory power.

    site_tables : {site_name: samples x features}; samples must align with
    target_df rows (target_df is samples x targets; its Euclidean distance
    matrix is the response).
    """
    sites_out = {}
    for site, table in site_tables.items():
        # Intersect subjects/rows first: reindexing would fabricate NaN rows
        # for subjects missing a site, and the NaN filter would then delete
        # innocent features.
        common = table.index.intersection(target_df.index)
        if len(common) < 6:
            sites_out[site] = {"error": f"only {len(common)} shared samples", "cumulative_r2": None,
                               "n_features_tested": 0, "n_significant": 0, "per_feature": []}
            continue
        site_dist = _euclidean_dist(target_df.loc[common])
        aligned = table.loc[common].dropna(axis=1, how="any")
        feats = aligned.columns
        if max_features_per_site and len(feats) > max_features_per_site:
            # rank by univariate association strength proxy: |Spearman| to
            # target centroid is costly; use variance as cheap pre-filter
            feats = aligned.var().sort_values(ascending=False).index[:max_features_per_site]
            aligned = aligned[feats]

        per_feature = []
        for feat in feats:
            res = db_permanova(aligned[[feat]], site_dist, n_perm=n_perm, seed=seed)
            t = res["terms"][0]
            per_feature.append({"feature": str(feat), "r2": t["r2"],
                                "pseudo_f": t["pseudo_f"], "pvalue": t["pvalue"]})
        per_feature.sort(key=lambda d: d["pvalue"])
        sig = [d["feature"] for d in per_feature if d["pvalue"] < p_threshold]

        if sig:
            cum = db_permanova(aligned[sig], site_dist, n_perm=n_perm, seed=seed)
            cum_r2 = cum["cumulative_r2"]
        else:
            cum_r2 = 0.0

        sites_out[site] = {
            "cumulative_r2": cum_r2,
            "n_features_tested": len(feats),
            "n_significant": len(sig),
            "per_feature": per_feature,
        }
    return {
        "method": "distance-based variance estimation (adonis2-style sequential PERMANOVA)",
        "reference": "Zhang et al., Microbiome 2026, doi:10.1186/s40168-026-02405-w",
        "p_threshold": p_threshold,
        "sites": sites_out,
    }


def _euclidean_dist(df: pd.DataFrame) -> np.ndarray:
    X = np.nan_to_num(np.asarray(df, dtype=float))
    sq = np.sum(X ** 2, axis=1)
    d2 = sq[:, None] + sq[None, :] - 2 * X @ X.T
    return np.sqrt(np.clip(d2, 0, None))


# ───────────────────────────────────────────────────────────────
# 2. Per-target GBDT / LASSO screen with nested CV
# ───────────────────────────────────────────────────────────────

def _spearman_preselect(Xtr: np.ndarray, ytr: np.ndarray, cols,
                        r_threshold: float, p_threshold: float):
    keep = []
    for j, c in enumerate(cols):
        r, p = stats.spearmanr(Xtr[:, j], ytr)
        if abs(r) >= r_threshold and p < p_threshold:
            keep.append((j, c, r, p))
    return keep


def cross_omics_gbdt_screen(
    feature_df: pd.DataFrame,
    target_df: pd.DataFrame,
    method: str = "gbdt",
    r_threshold: float = 0.3,
    p_threshold: float = 0.05,
    n_bootstrap: int = 20,
    cv_folds: int = 5,
    n_targets: Optional[int] = None,
    seed: int = 42,
    # GBDT hyperparameters follow the paper's tuned values
    n_estimators: int = 50,
    learning_rate: float = 0.01,
    min_samples_leaf: int = 8,
) -> Dict[str, Any]:
    """Per-target predictive screen: which features explain each target?

    Nested protocol (paper): feature pre-selection happens inside each
    training fold only (|Spearman r| >= 0.3 and p < 0.05), model is fit
    without access to held-out data, performance is the held-out R2
    distribution over bootstrap replicates x CV folds; per-target summary
    is mean R2 + 95% CI + one-sample t-test vs 0. Feature reproducibility
    = fraction of training iterations in which the feature was selected.

    method="lasso" uses LassoCV instead of GBDT (paper's second model).
    """
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.linear_model import LassoCV
    from sklearn.model_selection import KFold

    rng = np.random.default_rng(seed)
    X = np.nan_to_num(np.asarray(feature_df, dtype=float))
    feats = list(feature_df.columns)
    targets = list(target_df.columns)
    if n_targets:
        targets = targets[:n_targets]

    results = []
    for tcol in targets:
        y = np.nan_to_num(np.asarray(target_df[tcol], dtype=float))
        if np.std(y) == 0 or len(y) < cv_folds * 3:
            continue
        r2_scores: List[float] = []
        select_count = {f: 0 for f in feats}
        n_train_iters = 0

        for _ in range(n_bootstrap):
            kf = KFold(n_splits=cv_folds, shuffle=True,
                       random_state=int(rng.integers(1e9)))
            for tr, te in kf.split(X):
                n_train_iters += 1
                keep = _spearman_preselect(X[tr], y[tr], feats, r_threshold, p_threshold)
                if not keep:
                    continue
                for _, f, _, _ in keep:
                    select_count[f] += 1
                idx = [j for j, *_ in keep]
                if method == "lasso":
                    model = LassoCV(cv=3, max_iter=5000, random_state=seed)
                else:
                    model = GradientBoostingRegressor(
                        n_estimators=n_estimators, learning_rate=learning_rate,
                        min_samples_leaf=min_samples_leaf, random_state=seed)
                try:
                    model.fit(X[tr][:, idx], y[tr])
                    pred = model.predict(X[te][:, idx])
                    ss_res = float(np.sum((y[te] - pred) ** 2))
                    ss_tot = float(np.sum((y[te] - y[te].mean()) ** 2))
                    if ss_tot > 0:
                        r2_scores.append(1 - ss_res / ss_tot)
                except Exception:
                    continue

        if not r2_scores:
            continue
        arr = np.asarray(r2_scores)
        mean_r2 = float(arr.mean())
        ci = float(1.96 * arr.std(ddof=1) / np.sqrt(len(arr))) if len(arr) > 1 else 0.0
        t_stat, t_p = stats.ttest_1samp(arr, 0.0) if len(arr) > 1 else (np.nan, np.nan)
        repro = {f: c / n_train_iters for f, c in select_count.items() if c > 0 and n_train_iters}
        top = sorted(repro.items(), key=lambda kv: -kv[1])[:10]
        results.append({
            "target": str(tcol),
            "mean_r2": mean_r2,
            "ci95": ci,
            "t_pvalue": float(t_p) if not np.isnan(t_p) else None,
            "n_scores": len(arr),
            "n_features_selected": len(repro),
            "top_features": [{"feature": f, "reproducibility": round(r, 3)} for f, r in top],
        })

    # FDR over the per-target t-test p-values
    ps = [r["t_pvalue"] for r in results if r["t_pvalue"] is not None]
    if ps:
        adj = _bh_adjust(ps)
        i = 0
        for r in results:
            if r["t_pvalue"] is not None:
                r["t_padj"] = adj[i]
                i += 1
    results.sort(key=lambda r: -r["mean_r2"])
    return {
        "method": f"per-target {method.upper()} with nested CV + in-fold Spearman pre-selection",
        "reference": "Zhang et al., Microbiome 2026, doi:10.1186/s40168-026-02405-w",
        "params": {"r_threshold": r_threshold, "p_threshold": p_threshold,
                   "n_bootstrap": n_bootstrap, "cv_folds": cv_folds},
        "n_targets_modelled": len(results),
        "results": results,
    }


def _bh_adjust(pvals: List[float]) -> List[float]:
    """Benjamini-Hochberg FDR."""
    p = np.asarray(pvals)
    order = np.argsort(p)
    ranked = p[order] * len(p) / (np.arange(len(p)) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(ranked)
    out[order] = np.clip(ranked, 0, 1)
    return out.tolist()


# ───────────────────────────────────────────────────────────────
# 3. Correlation network per site
# ───────────────────────────────────────────────────────────────

def cross_site_correlation_network(
    site_tables: Dict[str, pd.DataFrame],
    target_df: pd.DataFrame,
    r_threshold: float = 0.3,
    p_threshold: float = 0.05,
    top_hubs: int = 5,
) -> Dict[str, Any]:
    """Spearman correlation network between each site's features and the
    target omics features. Reports per-site hub features (degree), shared
    targets (linked from multiple sites), and network centralities of the
    combined graph.
    """
    import networkx as nx

    G = nx.Graph()
    per_site_edges: Dict[str, List[Dict[str, Any]]] = {}
    target_sites: Dict[str, set] = {}

    for site, table in site_tables.items():
        common = table.index.intersection(target_df.index)
        aligned_feat = table.loc[common]
        target_sub = target_df.loc[common]
        edges = []
        for fcol in aligned_feat.columns:
            x = np.asarray(aligned_feat[fcol], dtype=float)
            if np.std(x) == 0:
                continue
            for tcol in target_sub.columns:
                y = np.asarray(target_sub[tcol], dtype=float)
                if np.std(y) == 0:
                    continue
                r, p = stats.spearmanr(x, y)
                if abs(r) >= r_threshold and p < p_threshold:
                    edges.append({"feature": str(fcol), "target": str(tcol),
                                  "r": float(r), "pvalue": float(p)})
                    G.add_edge(f"feat:{site}:{fcol}", f"target:{tcol}", weight=abs(r))
                    target_sites.setdefault(str(tcol), set()).add(site)
        # FDR within site
        if edges:
            adj = _bh_adjust([e["pvalue"] for e in edges])
            for e, a in zip(edges, adj):
                e["padj"] = a
        per_site_edges[site] = edges

    # centralities
    degree = dict(G.degree())
    betweenness = nx.betweenness_centrality(G) if G.number_of_nodes() else {}
    site_hubs = {}
    for site in site_tables:
        site_nodes = {n: d for n, d in degree.items() if n.startswith(f"feat:{site}:")}
        hubs = sorted(site_nodes.items(), key=lambda kv: -kv[1])[:top_hubs]
        site_hubs[site] = [{"feature": n.split(":", 2)[2], "degree": d} for n, d in hubs]

    shared = [
        {"target": t, "n_sites": len(s), "sites": sorted(s)}
        for t, s in target_sites.items() if len(s) >= 2
    ]
    shared.sort(key=lambda d: -d["n_sites"])

    return {
        "method": "Spearman correlation network (|r|>=threshold, p<threshold, BH-FDR per site)",
        "reference": "Zhang et al., Microbiome 2026, doi:10.1186/s40168-026-02405-w",
        "params": {"r_threshold": r_threshold, "p_threshold": p_threshold},
        "n_edges": G.number_of_edges(),
        "n_nodes": G.number_of_nodes(),
        "edges_per_site": {s: len(e) for s, e in per_site_edges.items()},
        "site_hubs": site_hubs,
        "shared_targets": shared[:25],
        "top_betweenness": sorted(
            ({"node": n, "betweenness": round(b, 4)} for n, b in betweenness.items()),
            key=lambda d: -d["betweenness"])[:10],
    }


# ───────────────────────────────────────────────────────────────
# 4. Cross-site disease concordance
# ───────────────────────────────────────────────────────────────

def cross_site_concordance(
    feature_tables: Dict[str, pd.DataFrame],
    metadata_df: pd.DataFrame,
    group_column: str,
    min_sites: int = 2,
    p_threshold: float = 0.05,
) -> Dict[str, Any]:
    """Which features are disease-associated in the SAME direction across
    multiple sites/omics?

    For every (site, feature): two-group comparison (Mann-Whitney) of the
    feature values between the metadata groups; FDR within each site;
    a feature is "concordant" when significant in >= min_sites sites with
    the same sign of effect (median difference).

    feature_tables : {layer_name: samples x features} -- layers can be
    body sites ("gut", "oral") or omics ("microbiome", "metabolome").
    metadata_df must be indexed by the same sample ids.
    """
    groups = metadata_df[group_column].dropna()
    levels = list(groups.unique())
    if len(levels) != 2:
        raise ValueError(f"group_column '{group_column}' needs exactly 2 levels, got {levels}")
    g0, g1 = levels[0], levels[1]

    per_layer: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for layer, table in feature_tables.items():
        common = table.index.intersection(groups.index)
        sub = table.loc[common]
        gmask = groups.loc[common]
        feats_out: Dict[str, Dict[str, Any]] = {}
        pvals, keys = [], []
        for col in sub.columns:
            a = sub.loc[gmask == g0, col].to_numpy(dtype=float)
            b = sub.loc[gmask == g1, col].to_numpy(dtype=float)
            a = a[~np.isnan(a)]
            b = b[~np.isnan(b)]
            if len(a) < 3 or len(b) < 3:
                continue
            u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
            direction = "up_in_" + str(g1) if np.median(b) > np.median(a) else "down_in_" + str(g1)
            feats_out[str(col)] = {"pvalue": float(p), "direction": direction,
                                   "median_g0": float(np.median(a)), "median_g1": float(np.median(b))}
            pvals.append(float(p))
            keys.append(str(col))
        if pvals:
            adj = _bh_adjust(pvals)
            for k, a_ in zip(keys, adj):
                feats_out[k]["padj"] = a_
        per_layer[layer] = feats_out

    # feature -> per-layer significant directions
    by_feature: Dict[str, List[tuple]] = {}
    for layer, feats in per_layer.items():
        for feat, res in feats.items():
            if res.get("padj", 1.0) < p_threshold:
                by_feature.setdefault(feat, []).append((layer, res["direction"], res["padj"]))

    concordant = []
    for feat, hits in by_feature.items():
        if len(hits) < min_sites:
            continue
        dirs = {d for _, d, _ in hits}
        concordant.append({
            "feature": feat,
            "n_layers_significant": len(hits),
            "layers": [l for l, _, _ in hits],
            "directions": sorted(dirs),
            "concordant_direction": len(dirs) == 1,
            "min_padj": min(p for _, _, p in hits),
        })
    concordant.sort(key=lambda d: (not d["concordant_direction"], -d["n_layers_significant"]))

    return {
        "method": "per-layer Mann-Whitney + BH-FDR; concordant = significant in >= min_sites layers with same direction",
        "reference": "Zhang et al., Microbiome 2026 (oral-gut axis IR vs IS analysis)",
        "group_column": group_column,
        "groups": [str(g0), str(g1)],
        "min_sites": min_sites,
        "n_features_tested_per_layer": {l: len(f) for l, f in per_layer.items()},
        "concordant_features": concordant,
    }


# ───────────────────────────────────────────────────────────────
# Data shaping helpers
# ───────────────────────────────────────────────────────────────

def subject_site_tables(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    site_column: Optional[str] = None,
    subject_column: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """Split a samples x features table into per-site subject-level tables.

    Cross-site comparisons link samples through the SUBJECT, not the row
    id (a gut swab and a plasma draw are different rows of the same
    person). Following the paper, longitudinal repeats are collapsed to
    per-(subject, site) means first, then each site becomes a
    subjects x features table.

    Returns {site: subjects x features}. When no site column exists the
    whole table is returned under a single "all" layer; when no subject
    column exists rows are treated as subjects already.
    """
    from app.services.multisite_analysis import _detect_site_column, _detect_subject_column

    meta = metadata_df.copy()
    site_col = site_column or _detect_site_column(meta)
    subj_col = subject_column or _detect_subject_column(meta)

    common = df.index.intersection(meta.index)
    df = df.loc[common]
    meta = meta.loc[common]

    if subj_col is None:
        meta["_subject_"] = meta.index.astype(str)
        subj_col = "_subject_"
    if site_col is None:
        return {"all": df.groupby(meta[subj_col]).mean(numeric_only=True)}

    out = {}
    for site, idx in meta.groupby(meta[site_col]).groups.items():
        sub = df.loc[idx]
        subjects = meta.loc[idx, subj_col]
        out[str(site)] = sub.groupby(subjects).mean(numeric_only=True)
    return out
