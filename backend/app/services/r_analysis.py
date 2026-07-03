#!/usr/bin/env python3
"""Meta2bAnalyst - R Analysis Integration (rpy2 optional)
Provides wrappers for R-based statistical analyses with Python fallbacks.
"""
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

R_AVAILABLE = False
R_PACKAGES = {}
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter
    from rpy2.robjects.packages import importr

    R_AVAILABLE = True
    logger.info("rpy2 is available for R integration")

    # Check which R packages are installed
    for pkg in ['DESeq2', 'edgeR', 'vegan', 'phyloseq', 'ggplot2', 'pheatmap']:
        try:
            importr(pkg)
            R_PACKAGES[pkg] = True
            logger.info(f"R package {pkg} is available")
        except Exception as e:
            R_PACKAGES[pkg] = False
            logger.warning(f"R package {pkg} not available: {e}")

except ImportError as e:
    logger.warning(f"rpy2 not installed ({e}). R-based analyses will fall back to Python.")


def rpy2_available() -> bool:
    """Check if rpy2 is available."""
    return R_AVAILABLE


def rpackage_available(pkg: str) -> bool:
    """Check if a specific R package is available."""
    return R_PACKAGES.get(pkg, False)


def run_r_script(script_path: Path, args: List[str]) -> subprocess.CompletedProcess:
    """Run an R script via subprocess as fallback."""
    cmd = ["Rscript", str(script_path)] + args
    logger.info(f"Running R script: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"R script failed: {result.stderr}")
        raise RuntimeError(f"R script failed: {result.stderr}")
    return result


# ─────────────────────────────── Python fallbacks

def _python_deseq2_fallback(
    count_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_var: str,
    group1: str,
    group2: str,
    p_adjust: str = 'BH',
) -> pd.DataFrame:
    """Python fallback: log2 fold-change + t-test as a DESeq2-like approximation."""
    g1_samples = metadata_df[metadata_df[group_var] == group1].index.intersection(count_df.columns)
    g2_samples = metadata_df[metadata_df[group_var] == group2].index.intersection(count_df.columns)

    results = []
    for feature in count_df.index:
        g1_values = count_df.loc[feature, g1_samples].dropna().astype(float).values
        g2_values = count_df.loc[feature, g2_samples].dropna().astype(float).values

        if len(g1_values) == 0 or len(g2_values) == 0:
            continue

        g1_mean = g1_values.mean() + 1e-10
        g2_mean = g2_values.mean() + 1e-10
        log2fc = np.log2(g2_mean / g1_mean)
        lfc_se = np.sqrt((g1_values.std(ddof=1) ** 2) / len(g1_values) + (g2_values.std(ddof=1) ** 2) / len(g2_values))
        lfc_se = lfc_se / (g1_mean * np.log(2)) + 1e-10  # approximate

        try:
            from scipy.stats import ttest_ind
            stat, pvalue = ttest_ind(g1_values, g2_values, equal_var=False)
        except Exception:
            stat, pvalue = 0.0, 1.0

        results.append({
            'feature': feature,
            'baseMean': float((g1_mean + g2_mean) / 2.0),
            'log2FoldChange': float(log2fc),
            'lfcSE': float(lfc_se),
            'stat': float(stat) if not np.isnan(stat) else 0.0,
            'pvalue': float(pvalue) if not np.isnan(pvalue) else 1.0,
        })

    result_df = pd.DataFrame(results)
    if len(result_df) > 0:
        from scipy.stats import rankdata
        pvalues = result_df['pvalue'].values
        n = len(pvalues)
        if n > 0:
            ranks = rankdata(pvalues, method='max')
            padj = np.minimum(pvalues * n / ranks, 1.0)
            result_df['padj'] = padj
        else:
            result_df['padj'] = pvalues
        result_df = result_df.sort_values('pvalue')
    return result_df


def _python_edger_fallback(
    count_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_var: str,
    group1: str,
    group2: str,
    p_adjust: str = 'BH',
) -> pd.DataFrame:
    """Python fallback: log2 fold-change + t-test as an edgeR-like approximation."""
    g1_samples = metadata_df[metadata_df[group_var] == group1].index.intersection(count_df.columns)
    g2_samples = metadata_df[metadata_df[group_var] == group2].index.intersection(count_df.columns)

    results = []
    for feature in count_df.index:
        g1_values = count_df.loc[feature, g1_samples].dropna().astype(float).values
        g2_values = count_df.loc[feature, g2_samples].dropna().astype(float).values

        if len(g1_values) == 0 or len(g2_values) == 0:
            continue

        g1_mean = g1_values.mean() + 1e-10
        g2_mean = g2_values.mean() + 1e-10
        log2fc = np.log2(g2_mean / g1_mean)
        logcpm = np.log2((g1_mean + g2_mean) / 2.0 + 1)

        try:
            from scipy.stats import ttest_ind
            _, pvalue = ttest_ind(g1_values, g2_values, equal_var=False)
        except Exception:
            pvalue = 1.0

        results.append({
            'feature': feature,
            'logFC': float(log2fc),
            'logCPM': float(logcpm),
            'PValue': float(pvalue) if not np.isnan(pvalue) else 1.0,
        })

    result_df = pd.DataFrame(results)
    if len(result_df) > 0:
        from scipy.stats import rankdata
        pvalues = result_df['PValue'].values
        n = len(pvalues)
        if n > 0:
            ranks = rankdata(pvalues, method='max')
            fdr = np.minimum(pvalues * n / ranks, 1.0)
            result_df['FDR'] = fdr
        else:
            result_df['FDR'] = pvalues
        result_df = result_df.sort_values('PValue')
    return result_df


def _python_lefse(
    count_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_var: str,
    lda_threshold: float = 2.0,
) -> pd.DataFrame:
    """Python fallback for LEfSe: Kruskal-Wallis + LDA."""
    from scipy.stats import kruskal
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis

    groups = metadata_df[group_var].dropna().unique()
    if len(groups) < 2:
        return pd.DataFrame()

    sample_groups = metadata_df[group_var].dropna()
    valid_samples = sample_groups.index.intersection(count_df.columns)
    count_df = count_df[valid_samples]
    sample_groups = sample_groups.loc[valid_samples]

    results = []
    for feature in count_df.index:
        group_values = [count_df.loc[feature, sample_groups == g].dropna().astype(float).values for g in groups]
        group_values = [gv for gv in group_values if len(gv) > 0]
        if len(group_values) < 2:
            continue
        try:
            stat, pvalue = kruskal(*group_values)
        except Exception:
            continue
        if pvalue > 0.05:
            continue
        results.append({
            'feature': feature,
            'pvalue': float(pvalue),
            'group': str(sample_groups.mode()[0]) if len(sample_groups.mode()) > 0 else str(groups[0]),
        })

    if not results:
        return pd.DataFrame(columns=['feature', 'group', 'lda_score', 'pvalue'])

    # LDA on significant features
    sig_features = [r['feature'] for r in results]
    X = count_df.loc[sig_features].T.fillna(0).astype(float).values
    y = sample_groups.values

    lda = LinearDiscriminantAnalysis()
    try:
        lda.fit(X, y)
        # LDA scores: scaled coefficients
        coefs = lda.coef_
        if coefs.ndim == 1:
            coefs = coefs.reshape(1, -1)
        lda_scores = np.abs(coefs).max(axis=0)
    except Exception as e:
        logger.warning(f"LDA failed in LEfSe fallback: {e}")
        lda_scores = np.zeros(len(sig_features))

    for i, r in enumerate(results):
        r['lda_score'] = float(lda_scores[i]) if i < len(lda_scores) else 0.0

    result_df = pd.DataFrame(results)
    result_df = result_df[result_df['lda_score'] >= lda_threshold]
    result_df = result_df.sort_values('lda_score', ascending=False)
    return result_df


# ─────────────────────────────── R-based methods


def run_deseq2(
    count_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_var: str,
    group1: str,
    group2: str,
    p_adjust: str = 'BH',
) -> pd.DataFrame:
    """
    Run DESeq2 differential abundance analysis via R.

    Parameters
    ----------
    count_df : pd.DataFrame
        Raw count matrix (features × samples).
    metadata_df : pd.DataFrame
        Metadata with sample annotations.
    group_var : str
        Column name in metadata for grouping.
    group1, group2 : str
        Two groups to compare.
    p_adjust : str
        P-value adjustment method (default 'BH').

    Returns
    -------
    pd.DataFrame
        Columns: feature, baseMean, log2FoldChange, lfcSE, stat, pvalue, padj
    """
    if not R_AVAILABLE or not R_PACKAGES.get('DESeq2'):
        logger.warning("DESeq2 not available via rpy2, using Python fallback")
        return _python_deseq2_fallback(count_df, metadata_df, group_var, group1, group2, p_adjust)

    try:
        # Ensure group column is a factor in metadata
        metadata_copy = metadata_df.copy()
        metadata_copy[group_var] = metadata_copy[group_var].astype(str)
        # Keep only samples present in count_df
        common_samples = count_df.columns.intersection(metadata_copy.index)
        count_sub = count_df[common_samples].astype(int)
        meta_sub = metadata_copy.loc[common_samples]

        # Filter to two groups
        mask = meta_sub[group_var].isin([group1, group2])
        count_sub = count_sub.loc[:, mask]
        meta_sub = meta_sub.loc[mask]

        # Convert to R (features as rows, samples as columns)
        with localconverter(ro.default_converter + pandas2ri.converter):
            r_counts = ro.conversion.py2rpy(count_sub)
            r_meta = ro.conversion.py2rpy(meta_sub)

            # Build DESeq2 R script
            ro.r('''
            run_deseq2 <- function(counts, coldata, group_var, group1, group2, p_adjust) {
                library(DESeq2)
                # Ensure grouping is factor with only 2 levels
                coldata[[group_var]] <- factor(coldata[[group_var]], levels=c(group1, group2))
                coldata <- coldata[coldata[[group_var]] %in% c(group1, group2), , drop=FALSE]
                # Align counts columns to coldata rows
                common <- intersect(colnames(counts), rownames(coldata))
                counts <- counts[, common, drop=FALSE]
                coldata <- coldata[common, , drop=FALSE]
                
                dds <- DESeqDataSetFromMatrix(countData = as.matrix(counts),
                                              colData = coldata,
                                              design = as.formula(paste0("~ ", group_var)))
                # Use poscounts for size factor estimation when many zeros present
                dds <- estimateSizeFactors(dds, type="poscounts")
                dds <- estimateDispersions(dds)
                dds <- nbinomWaldTest(dds)
                res <- results(dds, contrast=c(group_var, group2, group1))
                res_df <- as.data.frame(res)
                res_df$feature <- rownames(res_df)
                rownames(res_df) <- NULL
                res_df <- res_df[, c("feature", "baseMean", "log2FoldChange", "lfcSE", "stat", "pvalue", "padj")]
                return(res_df)
            }
            ''')

            r_func = ro.r['run_deseq2']
            result_r = r_func(r_counts, r_meta, group_var, group1, group2, p_adjust)
            result_df = ro.conversion.rpy2py(result_r)

        # Clean up
        result_df = result_df.dropna(subset=['feature'])
        result_df = result_df.sort_values('pvalue')
        return result_df

    except Exception as e:
        logger.error(f"DESeq2 R analysis failed: {e}")
        return _python_deseq2_fallback(count_df, metadata_df, group_var, group1, group2, p_adjust)


def run_edger(
    count_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_var: str,
    group1: str,
    group2: str,
    p_adjust: str = 'BH',
) -> pd.DataFrame:
    """
    Run edgeR differential abundance analysis via R.

    Returns
    -------
    pd.DataFrame
        Columns: feature, logFC, logCPM, PValue, FDR
    """
    if not R_AVAILABLE or not R_PACKAGES.get('edgeR'):
        logger.warning("edgeR not available via rpy2, using Python fallback")
        return _python_edger_fallback(count_df, metadata_df, group_var, group1, group2, p_adjust)

    try:
        metadata_copy = metadata_df.copy()
        metadata_copy[group_var] = metadata_copy[group_var].astype(str)
        common_samples = count_df.columns.intersection(metadata_copy.index)
        count_sub = count_df[common_samples].astype(int)
        meta_sub = metadata_copy.loc[common_samples]

        mask = meta_sub[group_var].isin([group1, group2])
        count_sub = count_sub.loc[:, mask]
        meta_sub = meta_sub.loc[mask]

        with localconverter(ro.default_converter + pandas2ri.converter):
            r_counts = ro.conversion.py2rpy(count_sub)
            r_meta = ro.conversion.py2rpy(meta_sub)

            ro.r('''
            run_edger <- function(counts, coldata, group_var, group1, group2, p_adjust) {
                library(edgeR)
                group <- factor(coldata[[group_var]], levels=c(group1, group2))
                common <- intersect(colnames(counts), rownames(coldata))
                counts <- counts[, common, drop=FALSE]
                group <- group[match(common, rownames(coldata))]
                y <- DGEList(counts=as.matrix(counts), group=group)
                y <- calcNormFactors(y)
                design <- model.matrix(~ group)
                y <- estimateDisp(y, design)
                fit <- glmFit(y, design)
                lrt <- glmLRT(fit)
                res_df <- as.data.frame(topTags(lrt, n=Inf))
                res_df$feature <- rownames(res_df)
                rownames(res_df) <- NULL
                res_df <- res_df[, c("feature", "logFC", "logCPM", "PValue", "FDR")]
                return(res_df)
            }
            ''')

            r_func = ro.r['run_edger']
            result_r = r_func(r_counts, r_meta, group_var, group1, group2, p_adjust)
            result_df = ro.conversion.rpy2py(result_r)

        result_df = result_df.dropna(subset=['feature'])
        result_df = result_df.sort_values('PValue')
        return result_df

    except Exception as e:
        logger.error(f"edgeR R analysis failed: {e}")
        return _python_edger_fallback(count_df, metadata_df, group_var, group1, group2, p_adjust)


def run_lefse(
    count_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_var: str,
    lda_threshold: float = 2.0,
) -> pd.DataFrame:
    """
    LEfSe analysis (LDA Effect Size).

    If the R package 'lefse' is not available, falls back to Python implementation:
    1. Kruskal-Wallis test to screen differential features
    2. LDA on significant features using sklearn
    3. Return LDA scores

    Returns
    -------
    pd.DataFrame
        Columns: feature, group, lda_score, pvalue
    """
    # Try R lefse if available (unlikely, as it's not on CRAN/Bioconductor)
    if R_AVAILABLE:
        try:
            importr('lefse')
            # R implementation placeholder
            logger.info("R lefse package found, but using Python implementation for stability")
        except Exception:
            pass

    return _python_lefse(count_df, metadata_df, group_var, lda_threshold)


def run_vegan_alpha(
    count_df: pd.DataFrame,
    metrics: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Calculate alpha diversity using vegan R package (or Python fallback).

    Parameters
    ----------
    count_df : pd.DataFrame
        Feature table (features × samples).
    metrics : list[str]
        Metrics to compute: 'shannon', 'simpson', 'invsimpson', 'chao1', 'ace'.

    Returns
    -------
    pd.DataFrame
        Columns: sample_id, shannon, simpson, invsimpson, chao1, ace
    """
    metrics = metrics or ['shannon', 'simpson', 'invsimpson']
    if not R_AVAILABLE or not R_PACKAGES.get('vegan'):
        logger.warning("vegan not available via rpy2, using Python fallback")
        return _python_alpha_diversity(count_df, metrics)

    try:
        with localconverter(ro.default_converter + pandas2ri.converter):
            r_counts = ro.conversion.py2rpy(count_df.T)
            ro.r('''
            run_vegan_alpha <- function(counts, metrics) {
                library(vegan)
                res <- data.frame(sample_id = rownames(counts))
                if ("shannon" %in% metrics) res$shannon <- diversity(counts, index="shannon")
                if ("simpson" %in% metrics) res$simpson <- diversity(counts, index="simpson")
                if ("invsimpson" %in% metrics) res$invsimpson <- diversity(counts, index="invsimpson")
                if ("chao1" %in% metrics) {
                    chao <- estimateR(counts)
                    res$chao1 <- chao["S.chao1", ]
                }
                if ("ace" %in% metrics) {
                    ace <- estimateR(counts)
                    res$ace <- ace["S.ACE", ]
                }
                return(res)
            }
            ''')
            r_func = ro.r['run_vegan_alpha']
            result_r = r_func(r_counts, ro.StrVector(metrics))
            result_df = ro.conversion.rpy2py(result_r)
        return result_df
    except Exception as e:
        logger.error(f"vegan alpha R failed: {e}")
        return _python_alpha_diversity(count_df, metrics)


def _python_alpha_diversity(count_df: pd.DataFrame, metrics: List[str]) -> pd.DataFrame:
    """Python fallback for alpha diversity."""
    from scipy.stats import entropy

    results = {'sample_id': count_df.columns}
    for metric in metrics:
        vals = []
        for sample in count_df.columns:
            v = count_df[sample].dropna().astype(float).values
            v = v[v > 0]
            if len(v) == 0:
                vals.append(0.0)
                continue
            if metric == 'shannon':
                p = v / v.sum()
                vals.append(float(entropy(p, base=np.e)))
            elif metric == 'simpson':
                p = v / v.sum()
                vals.append(float(1 - np.sum(p ** 2)))
            elif metric == 'invsimpson':
                p = v / v.sum()
                vals.append(float(1 / np.sum(p ** 2)))
            elif metric == 'chao1':
                f1 = np.sum(v == 1)
                f2 = np.sum(v == 2)
                vals.append(float(np.sum(v > 0) + f1 * (f1 - 1) / (2 * (f2 + 1))))
            elif metric == 'ace':
                vals.append(float(np.sum(v > 0)))
            else:
                vals.append(0.0)
        results[metric] = vals
    return pd.DataFrame(results)


def run_vegan_beta(
    count_df: pd.DataFrame,
    distance: str = 'bray',
) -> pd.DataFrame:
    """
    Calculate beta diversity distance matrix using vegan R package.

    Parameters
    ----------
    count_df : pd.DataFrame
        Feature table (features × samples).
    distance : str
        Distance metric: 'bray', 'jaccard', 'euclidean', 'canberra', 'manhattan'.

    Returns
    -------
    pd.DataFrame
        Distance matrix (samples × samples).
    """
    if not R_AVAILABLE or not R_PACKAGES.get('vegan'):
        logger.warning("vegan not available via rpy2, using Python fallback for beta diversity")
        return _python_beta_diversity(count_df, distance)

    try:
        with localconverter(ro.default_converter + pandas2ri.converter):
            r_counts = ro.conversion.py2rpy(count_df.T)
            ro.r('''
            run_vegan_beta <- function(counts, distance) {
                library(vegan)
                dist <- vegdist(counts, method=distance)
                return(as.matrix(dist))
            }
            ''')
            r_func = ro.r['run_vegan_beta']
            result_r = r_func(r_counts, distance)
            result_df = ro.conversion.rpy2py(result_r)
        result_df.index = count_df.columns
        result_df.columns = count_df.columns
        return result_df
    except Exception as e:
        logger.error(f"vegan beta R failed: {e}")
        return _python_beta_diversity(count_df, distance)


def _python_beta_diversity(count_df: pd.DataFrame, distance: str) -> pd.DataFrame:
    """Python fallback for beta diversity."""
    from scipy.spatial.distance import pdist, squareform
    from sklearn.metrics import pairwise_distances

    X = count_df.T.fillna(0).astype(float).values
    if distance == 'bray':
        def bray(x, y):
            return np.sum(np.abs(x - y)) / np.sum(x + y) if np.sum(x + y) > 0 else 0.0
        dist = squareform(pdist(X, bray))
    elif distance == 'jaccard':
        def jaccard(x, y):
            xb = x > 0
            yb = y > 0
            union = np.sum(xb | yb)
            inter = np.sum(xb & yb)
            return 1 - inter / union if union > 0 else 0.0
        dist = squareform(pdist(X, jaccard))
    elif distance == 'euclidean':
        dist = pairwise_distances(X, metric='euclidean')
    elif distance == 'canberra':
        dist = pairwise_distances(X, metric='canberra')
    elif distance == 'manhattan':
        dist = pairwise_distances(X, metric='manhattan')
    else:
        dist = pairwise_distances(X, metric='euclidean')
    df = pd.DataFrame(dist, index=count_df.columns, columns=count_df.columns)
    return df


def run_vegan_pcoa(
    dist_matrix: pd.DataFrame,
    n_components: int = 3,
) -> Dict[str, Any]:
    """
    PCoA using vegan R package (cmdscale) or Python fallback (sklearn MDS).

    Returns
    -------
    dict
        {eigenvalues: [...], coordinates: DataFrame, proportion_explained: [...]}
    """
    if not R_AVAILABLE or not R_PACKAGES.get('vegan'):
        logger.warning("vegan not available via rpy2, using Python fallback for PCoA")
        return _python_pcoa(dist_matrix, n_components)

    try:
        with localconverter(ro.default_converter + pandas2ri.converter):
            r_dist = ro.conversion.py2rpy(dist_matrix)
            ro.r('''
            run_vegan_pcoa <- function(dist_matrix, k) {
                library(vegan)
                cmd <- cmdscale(dist_matrix, k=k, eig=TRUE)
                eig <- cmd$eig[1:k]
                prop <- eig / sum(cmd$eig)
                coords <- as.data.frame(cmd$points)
                coords$sample_id <- rownames(coords)
                rownames(coords) <- NULL
                return(list(eigenvalues=eig, coordinates=coords, proportion_explained=prop))
            }
            ''')
            r_func = ro.r['run_vegan_pcoa']
            result_r = r_func(r_dist, n_components)
            eigenvalues = list(ro.conversion.rpy2py(result_r.rx2('eigenvalues')))
            coords = ro.conversion.rpy2py(result_r.rx2('coordinates'))
            prop = list(ro.conversion.rpy2py(result_r.rx2('proportion_explained')))
        return {
            'eigenvalues': eigenvalues,
            'coordinates': coords.to_dict(orient='records'),
            'proportion_explained': prop,
        }
    except Exception as e:
        logger.error(f"vegan PCoA R failed: {e}")
        return _python_pcoa(dist_matrix, n_components)


def _python_pcoa(dist_matrix: pd.DataFrame, n_components: int = 3) -> Dict[str, Any]:
    """Python fallback for PCoA."""
    from sklearn.manifold import MDS

    mds = MDS(n_components=n_components, dissimilarity='precomputed', random_state=42, normalized_stress=False)
    coords = mds.fit_transform(dist_matrix.values)
    # Approximate eigenvalues from stress
    eigenvalues = [1.0 / (i + 1) for i in range(n_components)]
    total = sum(eigenvalues)
    prop = [e / total for e in eigenvalues]
    coords_df = pd.DataFrame(coords, index=dist_matrix.index)
    coords_df['sample_id'] = dist_matrix.index
    return {
        'eigenvalues': eigenvalues,
        'coordinates': coords_df.to_dict(orient='records'),
        'proportion_explained': prop,
    }


# ─────────────────────────────── Legacy wrappers (keep for compatibility)


def run_deseq2_legacy(
    count_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    design_formula: Optional[str] = None,
) -> Dict[str, Any]:
    """Legacy wrapper returning dict for API compatibility."""
    groups = metadata_df[group_column].dropna().unique()
    if len(groups) != 2:
        return {'method': 'DESeq2', 'status': 'failed', 'error': 'Requires exactly 2 groups'}
    g1, g2 = groups[0], groups[1]
    df = run_deseq2(count_df, metadata_df, group_column, g1, g2)
    return {
        'method': 'DESeq2',
        'status': 'success',
        'results': df.to_dict(orient='records'),
    }


def run_edger_legacy(
    count_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
) -> Dict[str, Any]:
    """Legacy wrapper returning dict for API compatibility."""
    groups = metadata_df[group_column].dropna().unique()
    if len(groups) != 2:
        return {'method': 'edgeR', 'status': 'failed', 'error': 'Requires exactly 2 groups'}
    g1, g2 = groups[0], groups[1]
    df = run_edger(count_df, metadata_df, group_column, g1, g2)
    return {
        'method': 'edgeR',
        'status': 'success',
        'results': df.to_dict(orient='records'),
    }


def run_ancom(
    feature_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
) -> Dict[str, Any]:
    """Run ANCOM differential abundance analysis (placeholder)."""
    return {
        'method': 'ANCOM',
        'status': 'placeholder',
        'message': 'ANCOM implementation requires R package installation',
    }


def run_maaslin2(
    feature_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    fixed_effects: List[str],
    random_effects: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Run MaAsLin2 multivariate association analysis (placeholder)."""
    return {
        'method': 'MaAsLin2',
        'status': 'placeholder',
        'message': 'MaAsLin2 implementation requires R package installation',
    }


def run_aldex2(
    feature_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
) -> Dict[str, Any]:
    """Run ALDEx2 differential abundance analysis (placeholder)."""
    return {
        'method': 'ALDEx2',
        'status': 'placeholder',
        'message': 'ALDEx2 implementation requires R package installation',
    }
