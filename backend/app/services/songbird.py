"""
Songbird-style differential abundance analysis for microbiome data.

Implements multinomial logistic regression to estimate differential abundance
across groups. Feature abundances are used as predictors with group membership
as the response variable. Coefficients represent log-fold change estimates.

Uses only numpy, pandas, scipy, sklearn, statsmodels. No R required.
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, Any, Optional, Tuple


def _prepare_data(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """
    Align and prepare feature table and group labels.
    
    Parameters
    ----------
    df : pd.DataFrame
        Feature abundance table (samples x features).
    metadata_df : pd.DataFrame
        Sample metadata with sample IDs as index.
    group_column : str
        Column name in metadata_df containing group labels.
    
    Returns
    -------
    tuple : (X_train, y_train, X_clr, groups)
        X_train : feature matrix for modeling
        y_train : group labels
        X_clr : CLR-transformed features
        groups : aligned group series
    """
    if group_column not in metadata_df.columns:
        raise ValueError(f"Group column '{group_column}' not found in metadata.")
    
    # Align samples
    common_samples = df.index.intersection(metadata_df.index)
    if len(common_samples) == 0:
        raise ValueError("No matching sample IDs between feature table and metadata.")
    
    X = df.loc[common_samples].copy()
    groups = metadata_df.loc[common_samples, group_column]
    
    # Remove samples with missing group labels
    valid_mask = groups.notna()
    X = X.loc[valid_mask]
    groups = groups.loc[valid_mask]
    
    if len(groups) < 4:
        raise ValueError(f"Need at least 4 samples, found {len(groups)}.")
    
    # CLR transform for effect size interpretation
    X_pseudo = X + 0.5
    log_vals = np.log(X_pseudo)
    row_means = log_vals.mean(axis=1)
    X_clr = log_vals.subtract(row_means, axis=0)
    
    return X, groups, X_clr, groups


def _fit_sklearn_multinomial(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list,
    groups: np.ndarray,
    max_iter: int = 1000,
    learning_rate: float = 0.001,
    regularization: str = 'l2',
    C: float = 1.0
) -> Dict[str, Any]:
    """
    Fit multinomial logistic regression using sklearn.
    
    Parameters
    ----------
    X : np.ndarray
        Feature matrix (n_samples x n_features).
    y : np.ndarray
        Group labels (n_samples,).
    feature_names : list
        List of feature names.
    groups : np.ndarray
        Unique group labels.
    max_iter : int, default=1000
        Maximum iterations for solver.
    learning_rate : float, default=0.001
        Not directly used in sklearn but kept for API compatibility.
    regularization : str, default='l2'
        Regularization type ('l1', 'l2', 'elasticnet', 'none').
    C : float, default=1.0
        Inverse regularization strength (smaller = stronger regularization).
    
    Returns
    -------
    dict : Model results with coefficients, p-values, and diagnostics.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import log_loss, accuracy_score
    
    # Standardize features for stable convergence
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Handle regularization parameter
    if regularization == 'none':
        penalty = None
        C = 1.0  # ignored when penalty is None
    else:
        penalty = regularization
    
    # Fit multinomial logistic regression
    # Use 'saga' solver for all regularization types including l1 and elasticnet
    if penalty in ('l1', 'elasticnet'):
        solver = 'saga'
        l1_ratio = 0.5 if penalty == 'elasticnet' else None
    else:
        solver = 'lbfgs'
        l1_ratio = None
    
    # sklearn >= 1.7 removed the multi_class kwarg (lbfgs/saga have defaulted
    # to multinomial since 0.22), so passing it broke on current sklearn.
    model = LogisticRegression(
        solver=solver,
        penalty=penalty,
        C=C,
        max_iter=max_iter,
        l1_ratio=l1_ratio,
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(X_scaled, y)
    
    # Predictions and diagnostics
    y_pred = model.predict(X_scaled)
    y_prob = model.predict_proba(X_scaled)
    
    accuracy = accuracy_score(y, y_pred)
    logloss = log_loss(y, y_prob)
    
    # Extract coefficients
    # shape: (n_classes, n_features) for true multinomial fits
    coefs = model.coef_
    intercepts = model.intercept_

    classes = model.classes_

    # sklearn fits binary problems as a single log-odds vector (coef_ has one
    # row) regardless of multi_class. Expand to the per-class layout the
    # result table expects: with +/- w/2 the class log-ratio equals sklearn's
    # binary log-odds w.x, so coefficient *differences* stay interpretable.
    if len(classes) == 2 and coefs.shape[0] == 1:
        coefs = np.vstack([-coefs / 2.0, coefs / 2.0])
        intercepts = np.concatenate([-intercepts / 2.0, intercepts / 2.0])
    
    # Approximate p-values using Wald test (coef / std_err)
    # Standard error approximated via Fisher information
    # This is a rough approximation; for exact p-values use statsmodels
    n_samples, n_features = X_scaled.shape
    n_classes = len(classes)
    
    # Compute standard errors (simplified approximation)
    # For multinomial: Var(coef) ≈ (X'X)^(-1) * dispersion
    # We'll use a sandwich estimator approximation
    try:
        XtX_inv = np.linalg.inv(np.dot(X_scaled.T, X_scaled) / n_samples + 1e-6 * np.eye(n_features))
        dispersion = logloss * n_samples / (n_samples - n_features * n_classes)
        std_errs = np.sqrt(np.outer(np.diag(XtX_inv), np.ones(n_classes)).T * dispersion)
    except np.linalg.LinAlgError:
        std_errs = np.ones_like(coefs) * 0.5
    
    z_scores = coefs / (std_errs + 1e-10)
    pvalues = 2 * (1 - stats.norm.cdf(np.abs(z_scores)))
    
    # Build results per feature
    results = []
    for i, feat in enumerate(feature_names):
        feat_dict = {'feature': feat}
        for j, cls in enumerate(classes):
            feat_dict[f'coef_{cls}'] = float(coefs[j, i])
            feat_dict[f'stderr_{cls}'] = float(std_errs[j, i])
            feat_dict[f'zscore_{cls}'] = float(z_scores[j, i])
            feat_dict[f'pvalue_{cls}'] = float(pvalues[j, i])
        results.append(feat_dict)
    
    results_df = pd.DataFrame(results)
    
    # Compute overall feature importance (max |coefficient| across classes)
    coef_cols = [c for c in results_df.columns if c.startswith('coef_')]
    results_df['max_abs_coef'] = results_df[coef_cols].abs().max(axis=1)
    results_df['mean_abs_coef'] = results_df[coef_cols].abs().mean(axis=1)
    
    return {
        'model': model,
        'results_df': results_df,
        'classes': classes,
        'coefficients': coefs,
        'intercepts': intercepts,
        'accuracy': float(accuracy),
        'log_loss': float(logloss),
        'n_iter': model.n_iter_,
        'converged': model.n_iter_ < max_iter
    }


def _fit_statsmodels_multinomial(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list,
    max_iter: int = 1000
) -> Dict[str, Any]:
    """
    Fit multinomial logistic regression using statsmodels for exact p-values.
    
    Parameters
    ----------
    X : np.ndarray
        Feature matrix.
    y : np.ndarray
        Group labels.
    feature_names : list
        Feature names.
    max_iter : int, default=1000
        Maximum iterations.
    
    Returns
    -------
    dict : Model results with exact p-values and confidence intervals.
    """
    import statsmodels.api as sm
    from sklearn.preprocessing import LabelEncoder
    
    # Statsmodels MNLogit requires numeric endog starting from 0
    le = LabelEncoder()
    y_encoded = le.fit_transform(y)
    
    # Add constant (intercept)
    X_const = sm.add_constant(X, has_constant='add')
    
    # Fit model
    model = sm.MNLogit(y_encoded, X_const)
    
    try:
        result = model.fit(disp=0, maxiter=max_iter)
        
        # Extract parameters
        params = result.params  # (n_features+1, n_classes-1)
        pvalues = result.pvalues
        conf_int = result.conf_int()
        
        n_classes = len(le.classes_)
        n_features = len(feature_names)
        
        # Build results - params excludes reference class
        results = []
        for i, feat in enumerate(['intercept'] + feature_names):
            feat_dict = {'feature': feat}
            for j in range(params.shape[1]):
                cls_name = le.classes_[j + 1] if (j + 1) < len(le.classes_) else f"class_{j+1}"
                feat_dict[f'coef_{cls_name}'] = float(params.iloc[i, j])
                feat_dict[f'pvalue_{cls_name}'] = float(pvalues.iloc[i, j])
                if conf_int is not None:
                    feat_dict[f'ci_low_{cls_name}'] = float(conf_int.iloc[i, j, 0])
                    feat_dict[f'ci_high_{cls_name}'] = float(conf_int.iloc[i, j, 1])
            results.append(feat_dict)
        
        results_df = pd.DataFrame(results)
        
        # Feature importance (exclude intercept)
        feat_df = results_df[results_df['feature'] != 'intercept'].copy()
        coef_cols = [c for c in feat_df.columns if c.startswith('coef_')]
        feat_df['max_abs_coef'] = feat_df[coef_cols].abs().max(axis=1)
        feat_df['mean_abs_coef'] = feat_df[coef_cols].abs().mean(axis=1)
        
        return {
            'model': result,
            'results_df': feat_df,
            'classes': le.classes_,
            'params': params,
            'pvalues': pvalues,
            'aic': float(result.aic),
            'bic': float(result.bic),
            'loglikelihood': float(result.llf),
            'pseudo_r2': float(result.prsquared) if hasattr(result, 'prsquared') else None,
            'converged': result.mle_retvals.get('converged', True),
            'n_iter': result.mle_retvals.get('iterations', 0)
        }
    
    except Exception as e:
        # Fallback to sklearn if statsmodels fails
        return _fit_sklearn_multinomial(X, y, feature_names, le.classes_, max_iter=max_iter)


def run_songbird(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    epochs: int = 1000,
    learning_rate: float = 0.001,
    backend: str = 'auto',
    regularization: str = 'l2',
    C: float = 1.0,
    clr_transform: bool = True,
    top_n: int = 50
) -> Dict[str, Any]:
    """
    Run Songbird-style differential abundance analysis using multinomial regression.
    
    Fits a multinomial logistic regression model with group membership as the
    response and feature abundances as predictors. Coefficients are interpreted
    as log-fold change estimates.
    
    Parameters
    ----------
    df : pd.DataFrame
        Feature abundance table (samples x features) with non-negative values.
    metadata_df : pd.DataFrame
        Sample metadata with sample IDs as index.
    group_column : str
        Column name in metadata_df containing group labels.
    epochs : int, default=1000
        Maximum iterations (mapped to sklearn's max_iter).
    learning_rate : float, default=0.001
        Learning rate hint (primarily for API compatibility; sklearn uses solver-specific rates).
    backend : str, default='auto'
        Backend to use: 'auto', 'statsmodels', or 'sklearn'.
    regularization : str, default='l2'
        Regularization type for sklearn backend.
    C : float, default=1.0
        Inverse regularization strength for sklearn backend.
    clr_transform : bool, default=True
        Whether to use CLR-transformed data for effect size reporting.
    top_n : int, default=50
        Number of top features to include in ranked plot.
    
    Returns
    -------
    dict
        {
            'plot_data': {
                'ranked_coefficients': {
                    'feature_ids': list[str],
                    'coefficients': list[list[float]],  # per class
                    'classes': list[str],
                    'colors': list[str]
                },
                'volcano_style': {  # coefficient vs -log10(p)
                    'x': list[float],
                    'y': list[float],
                    'feature_ids': list[str]
                }
            },
            'statistics': {
                'n_features': int,
                'n_samples': int,
                'n_classes': int,
                'accuracy': float,
                'log_loss': float,
                'converged': bool,
                'n_iter': int,
                'top_positive': list[str],   # top features positively associated
                'top_negative': list[str],   # top features negatively associated
                'backend': str
            },
            'results_table': pd.DataFrame
        }
    """
    # Prepare data
    X_raw, groups, X_clr, _ = _prepare_data(df, metadata_df, group_column)
    
    n_samples, n_features = X_raw.shape
    unique_groups = groups.unique()
    n_classes = len(unique_groups)
    feature_names = list(X_raw.columns)
    
    # Use raw counts/proportions for modeling (multinomial assumption)
    X_model = X_raw.values.astype(float)
    y = groups.values
    
    # Add small pseudocount for numerical stability
    X_model = X_model + 0.5
    
    # Choose backend
    if backend == 'auto':
        try:
            import statsmodels.api as sm
            backend = 'statsmodels'
        except ImportError:
            backend = 'sklearn'
    
    # Fit model
    if backend == 'statsmodels':
        fit_results = _fit_statsmodels_multinomial(
            X_model, y, feature_names, max_iter=epochs
        )
    else:
        fit_results = _fit_sklearn_multinomial(
            X_model, y, feature_names, unique_groups,
            max_iter=epochs, learning_rate=learning_rate,
            regularization=regularization, C=C
        )
    
    results_df = fit_results['results_df'].copy()
    classes = fit_results['classes']
    
    # Sort by importance for ranked plot
    results_df = results_df.sort_values('max_abs_coef', ascending=False)
    
    # Top N features for plotting
    plot_df = results_df.head(top_n).copy()
    
    # Build plot data: ranked coefficients
    coef_cols = [c for c in plot_df.columns if c.startswith('coef_')]
    
    # Reorder by mean absolute coefficient for cleaner visualization
    plot_df = plot_df.sort_values('mean_abs_coef', ascending=True)
    
    ranked_data = {
        'feature_ids': plot_df['feature'].tolist(),
        'coefficients': [],
        'classes': [c.replace('coef_', '') for c in coef_cols],
        'colors': _get_class_colors(len(coef_cols))
    }
    
    for col in coef_cols:
        ranked_data['coefficients'].append(plot_df[col].tolist())
    
    # Volcano-style plot data (first non-intercept class coefficient vs significance)
    if len(coef_cols) > 0:
        first_coef_col = coef_cols[0]
        first_pval_col = first_coef_col.replace('coef_', 'pvalue_')
        
        if first_pval_col in results_df.columns:
            pvals = results_df[first_pval_col].values
        else:
            pvals = np.ones(len(results_df))
        
        log_pvals = -np.log10(np.maximum(pvals, 1e-300))
        
        volcano_data = {
            'x': results_df[first_coef_col].tolist(),
            'y': log_pvals.tolist(),
            'feature_ids': results_df['feature'].tolist()
        }
    else:
        volcano_data = {'x': [], 'y': [], 'feature_ids': []}
    
    # Identify top positive and negative features (by first class coefficient)
    if len(coef_cols) > 0:
        first_coef = coef_cols[0]
        top_pos = results_df.nlargest(10, first_coef)['feature'].tolist()
        top_neg = results_df.nsmallest(10, first_coef)['feature'].tolist()
    else:
        top_pos = []
        top_neg = []
    
    plot_data = {
        'ranked_coefficients': ranked_data,
        'volcano_style': volcano_data
    }
    
    stats_summary = {
        'n_features': n_features,
        'n_samples': n_samples,
        'n_classes': n_classes,
        'classes': [str(c) for c in classes],
        'accuracy': fit_results.get('accuracy', None),
        'log_loss': fit_results.get('log_loss', None),
        'aic': fit_results.get('aic', None),
        'bic': fit_results.get('bic', None),
        'converged': fit_results.get('converged', False),
        'n_iter': fit_results.get('n_iter', 0),
        'top_positive': top_pos,
        'top_negative': top_neg,
        'backend': backend
    }
    
    return {
        'plot_data': plot_data,
        'statistics': stats_summary,
        'results_table': results_df,
        'model': fit_results.get('model')
    }


def _get_class_colors(n: int) -> list:
    """Generate distinct colors for classes."""
    base_colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
    ]
    if n <= len(base_colors):
        return base_colors[:n]
    
    # Generate additional colors using HSV
    colors = []
    for i in range(n):
        h = i / n
        s = 0.7 + 0.3 * (i % 2)
        v = 0.8 + 0.2 * ((i // 2) % 2)
        # HSV to RGB
        c = v * s
        x = c * (1 - abs((h * 6) % 2 - 1))
        m = v - c
        
        if h < 1/6:
            r, g, b = c, x, 0
        elif h < 2/6:
            r, g, b = x, c, 0
        elif h < 3/6:
            r, g, b = 0, c, x
        elif h < 4/6:
            r, g, b = 0, x, c
        elif h < 5/6:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        
        rgb = tuple(int((v + m) * 255) for v in [r, g, b])
        colors.append(f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")
    
    return colors


# API compatibility alias
def run_songbird_analysis(df, metadata_df, group_column, **kwargs):
    """Alias for run_songbird for backward compatibility."""
    return run_songbird(df, metadata_df, group_column, **kwargs)
