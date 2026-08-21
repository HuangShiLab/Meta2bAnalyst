"""
Meta2bAnalyst - mmvec Backend Service
======================================
Neural network microbe-metabolite conditional co-occurrence modelling.

mmvec (Morton & Marotz et al. 2019) learns low-dimensional embeddings
U (microbes) and V (metabolites) such that the conditional probability
of observing a metabolite given a microbe sample is modelled via a
bilinear form followed by softmax.

This module provides:
1. A lightweight PyTorch implementation (preferred).
2. A fast NumPy SVD fallback when PyTorch is unavailable.

References
----------
- Morton & Marotz et al. 2019, mSystems 4:e00020-19.
- https://github.com/biocore/mmvec

Author: Meta2b Analyst Team
"""

import json
import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ─────────────────────────────── PyTorch availability probe
TORCH_AVAILABLE = False
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.optim import Adam

    TORCH_AVAILABLE = True
    logger.info("PyTorch available in mmvec module")
except ImportError:
    logger.warning(
        "PyTorch not installed; mmvec will fall back to NumPy SVD approximation."
    )


# ─────────────────────────────── Helpers

def _clr_transform(df: pd.DataFrame, pseudo_count: float = 1e-6) -> pd.DataFrame:
    """Centered Log-Ratio transformation for compositional microbiome data."""
    vals = df.values.astype(float)
    vals = np.where(vals < 0, 0, vals)
    vals = vals + pseudo_count
    log_vals = np.log(vals)
    gm = log_vals.mean(axis=1, keepdims=True)
    clr = log_vals - gm
    return pd.DataFrame(clr, index=df.index, columns=df.columns)


def _log_transform(df: pd.DataFrame, offset: float = 1e-6) -> pd.DataFrame:
    """Log-transform metabolome data (handles zeros with offset)."""
    vals = df.values.astype(float)
    vals = np.where(vals < 0, 0, vals)
    vals = vals + offset
    return pd.DataFrame(np.log(vals), index=df.index, columns=df.columns)


def _softmax_rows(x: np.ndarray) -> np.ndarray:
    """Row-wise softmax for a 2-D NumPy array."""
    e_x = np.exp(x - np.max(x, axis=1, keepdims=True))
    return e_x / (e_x.sum(axis=1, keepdims=True) + 1e-12)


# ─────────────────────────────── PyTorch Model (only defined when torch available)
if TORCH_AVAILABLE:
    class _MMvecModel(nn.Module):
        """
        Simplified mmvec: bilinear interaction + bias terms.

        Given a microbiome sample vector x ( microbes ), we compute logits::

            logits = x @ U @ V.T + b_v

        where U (n_microbes × latent_dim) and V (n_metabolites × latent_dim)
        are learnable embeddings, and b_v is a metabolite bias.

        The conditional probability P(metabolite | sample) is softmax(logits).
        """

        def __init__(
            self,
            n_microbes: int,
            n_metabolites: int,
            latent_dim: int = 50,
        ):
            super().__init__()
            self.n_microbes = n_microbes
            self.n_metabolites = n_metabolites
            self.latent_dim = latent_dim

            # Microbe embeddings U
            self.U = nn.Parameter(torch.randn(n_microbes, latent_dim) * 0.01)
            # Metabolite embeddings V
            self.V = nn.Parameter(torch.randn(n_metabolites, latent_dim) * 0.01)
            # Bias per metabolite
            self.b_v = nn.Parameter(torch.zeros(n_metabolites))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """
            Parameters
            ----------
            x : torch.Tensor, shape (batch, n_microbes)
                Microbiome composition (CLR or relative abundance).

            Returns
            -------
            logits : torch.Tensor, shape (batch, n_metabolites)
            """
            # x @ U  →  (batch, latent_dim)
            h = torch.matmul(x, self.U)
            # h @ V.T + b_v  →  (batch, n_metabolites)
            logits = torch.matmul(h, self.V.t()) + self.b_v
            return logits

        def conditional_prob(self, x: torch.Tensor) -> torch.Tensor:
            """Return P(metabolite | sample) as softmax probabilities."""
            logits = self.forward(x)
            return F.softmax(logits, dim=1)


    # ─────────────────────────────── PyTorch Training

    def _train_mmvec_torch(
        X_mb: np.ndarray,
        Y_mt: np.ndarray,
        latent_dim: int = 50,
        epochs: int = 1000,
        learning_rate: float = 0.001,
        batch_size: Optional[int] = None,
        early_stop_patience: int = 50,
        random_state: int = 42,
    ) -> Dict[str, Any]:
        """
        Train mmvec with PyTorch.

        Parameters
        ----------
        X_mb : np.ndarray, shape (n_samples, n_microbes)
        Y_mt : np.ndarray, shape (n_samples, n_metabolites)
        latent_dim : int
        epochs : int
        learning_rate : float
        batch_size : int or None
            If None, full-batch training.
        early_stop_patience : int
            Stop if validation loss does not improve for N epochs.
        random_state : int

        Returns
        -------
        dict with trained weights and loss history.
        """
        torch.manual_seed(random_state)
        n_samples, n_microbes = X_mb.shape
        _, n_metabolites = Y_mt.shape

        # Convert to torch tensors
        X_tensor = torch.from_numpy(X_mb).float()
        Y_tensor = torch.from_numpy(Y_mt).float()

        # Train / validation split (80 / 20)
        n_train = int(0.8 * n_samples)
        perm = torch.randperm(n_samples)
        train_idx = perm[:n_train]
        val_idx = perm[n_train:]

        X_train, Y_train = X_tensor[train_idx], Y_tensor[train_idx]
        X_val, Y_val = X_tensor[val_idx], Y_tensor[val_idx]

        model = _MMvecModel(n_microbes, n_metabolites, latent_dim)
        optimizer = Adam(model.parameters(), lr=learning_rate)

        # Normalise Y to probabilities per sample (for cross-entropy target)
        Y_train_prob = Y_train / (Y_train.sum(dim=1, keepdim=True) + 1e-12)
        Y_val_prob = Y_val / (Y_val.sum(dim=1, keepdim=True) + 1e-12)

        loss_history = []
        val_loss_history = []
        best_val_loss = float("inf")
        patience_counter = 0

        batch_size = batch_size or n_train
        n_batches = max(1, n_train // batch_size)

        for epoch in range(epochs):
            model.train()
            epoch_losses = []
            for b in range(n_batches):
                start = b * batch_size
                end = min(start + batch_size, n_train)
                xb = X_train[start:end]
                yb = Y_train_prob[start:end]

                logits = model(xb)
                # Negative log-likelihood ≈ cross-entropy against target distribution
                log_probs = F.log_softmax(logits, dim=1)
                loss = -(yb * log_probs).sum() / yb.size(0)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                epoch_losses.append(loss.item())

            avg_loss = float(np.mean(epoch_losses))
            loss_history.append(avg_loss)

            # Validation
            model.eval()
            with torch.no_grad():
                val_logits = model(X_val)
                val_log_probs = F.log_softmax(val_logits, dim=1)
                val_loss = -(Y_val_prob * val_log_probs).sum() / Y_val_prob.size(0)
                val_loss_f = val_loss.item()
            val_loss_history.append(val_loss_f)

            if val_loss_f < best_val_loss:
                best_val_loss = val_loss_f
                patience_counter = 0
                # Save best state dict
                best_state = {
                    "U": model.U.detach().cpu().numpy().copy(),
                    "V": model.V.detach().cpu().numpy().copy(),
                    "b_v": model.b_v.detach().cpu().numpy().copy(),
                }
            else:
                patience_counter += 1

            if patience_counter >= early_stop_patience:
                logger.info(f"mmvec early stopping at epoch {epoch + 1}")
                break

            if (epoch + 1) % 200 == 0:
                logger.info(
                    f"mmvec epoch {epoch + 1}/{epochs}  "
                    f"train_loss={avg_loss:.4f}  val_loss={val_loss_f:.4f}"
                )

        # Restore best weights
        U = best_state["U"]
        V = best_state["V"]
        b_v = best_state["b_v"]

        # Conditional probability on full data
        model.eval()
        with torch.no_grad():
            full_logits = model(X_tensor)
            cond_prob = F.softmax(full_logits, dim=1).cpu().numpy()

        return {
            "U": U,
            "V": V,
            "b_v": b_v,
            "conditional_prob": cond_prob,
            "loss_history": loss_history,
            "val_loss_history": val_loss_history,
        }


# ─────────────────────────────── NumPy SVD Fallback

def _mmvec_numpy_fallback(
    X_mb: np.ndarray,
    Y_mt: np.ndarray,
    latent_dim: int = 50,
) -> Dict[str, Any]:
    """
    Fast non-probabilistic approximation using SVD on the co-occurrence matrix.

    We form the (normalised) co-occurrence matrix C = X.T @ Y,
    then perform truncated SVD: C ≈ U_diag @ S @ V_diag.T.
    The latent embeddings are scaled singular vectors.

    Returns the same keys as the PyTorch path for downstream compatibility.
    """
    n_samples, n_microbes = X_mb.shape
    _, n_metabolites = Y_mt.shape

    # Row-normalise inputs
    X_norm = X_mb / (X_mb.sum(axis=1, keepdims=True) + 1e-12)
    Y_norm = Y_mt / (Y_mt.sum(axis=1, keepdims=True) + 1e-12)

    # Co-occurrence
    C = (X_norm.T @ Y_norm) / n_samples  # (n_microbes, n_metabolites)

    # Truncated SVD
    k = min(latent_dim, n_microbes, n_metabolites)
    U_svd, s, Vh = np.linalg.svd(C, full_matrices=False)
    U_emb = U_svd[:, :k] * np.sqrt(s[:k])  # (n_microbes, k)
    V_emb = Vh.T[:, :k] * np.sqrt(s[:k])   # (n_metabolites, k)

    # Reconstruct conditional logits via bilinear form
    logits = X_norm @ U_emb @ V_emb.T  # (n_samples, n_metabolites)
    cond_prob = _softmax_rows(logits)

    return {
        "U": U_emb,
        "V": V_emb,
        "b_v": np.zeros(n_metabolites),
        "conditional_prob": cond_prob,
        "loss_history": [],
        "val_loss_history": [],
        "note": "NumPy SVD fallback — non-probabilistic approximation",
    }


# ─────────────────────────────── Biplot

def _build_biplot(
    U: np.ndarray,
    V: np.ndarray,
    microbe_names: pd.Index,
    metabolite_names: pd.Index,
    top_n: int = 30,
) -> Dict[str, Any]:
    """
    Build an interactive biplot of U and V in the first two latent dimensions.

    Parameters
    ----------
    U, V : np.ndarray
        Embeddings arrays (n_microbes × latent_dim, n_metabolites × latent_dim).
    microbe_names, metabolite_names : pd.Index
    top_n : int
        Show only the top N features by L2 norm in latent space.

    Returns
    -------
    plotly figure dict.
    """
    # Select top features by magnitude in latent space
    u_norms = np.linalg.norm(U, axis=1)
    v_norms = np.linalg.norm(V, axis=1)

    u_top_idx = np.argsort(-u_norms)[: min(top_n, len(u_norms))]
    v_top_idx = np.argsort(-v_norms)[: min(top_n, len(v_norms))]

    fig = go.Figure()

    # Microbes
    fig.add_trace(
        go.Scatter(
            x=U[u_top_idx, 0],
            y=U[u_top_idx, 1],
            mode="markers+text",
            name="Microbes",
            text=[str(microbe_names[i]) for i in u_top_idx],
            textposition="top center",
            marker=dict(size=10, color="#2E86AB", opacity=0.8, symbol="circle"),
            hovertemplate="<b>%{text}</b><br>Dim1: %{x:.3f}<br>Dim2: %{y:.3f}<extra></extra>",
        )
    )

    # Metabolites
    fig.add_trace(
        go.Scatter(
            x=V[v_top_idx, 0],
            y=V[v_top_idx, 1],
            mode="markers+text",
            name="Metabolites",
            text=[str(metabolite_names[i]) for i in v_top_idx],
            textposition="bottom center",
            marker=dict(size=10, color="#A23B72", opacity=0.8, symbol="diamond"),
            hovertemplate="<b>%{text}</b><br>Dim1: %{x:.3f}<br>Dim2: %{y:.3f}<extra></extra>",
        )
    )

    fig.update_layout(
        title="mmvec Biplot — Latent Dim 1 vs Dim 2",
        xaxis_title="Latent Dimension 1",
        yaxis_title="Latent Dimension 2",
        template="plotly_white",
        width=750,
        height=650,
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5
        ),
    )
    return fig.to_dict()


# ─────────────────────────────── Public API

def run_mmvec(
    microbiome_df: pd.DataFrame,
    metabolome_df: pd.DataFrame,
    epochs: int = 1000,
    latent_dim: int = 50,
    learning_rate: float = 0.001,
) -> Dict[str, Any]:
    """
    mmvec: Neural network microbe-metabolite conditional co-occurrence.

    Parameters
    ----------
    microbiome_df : pd.DataFrame
        Sample × microbe matrix (counts or relative abundance).
    metabolome_df : pd.DataFrame
        Sample × metabolite matrix (will be log-transformed internally).
    epochs : int, default 1000
        Number of training epochs (PyTorch path).
    latent_dim : int, default 50
        Dimensionality of the latent embedding space.
    learning_rate : float, default 0.001
        Adam learning rate.

    Returns
    -------
    dict
        {
            "conditional_prob_matrix": pd.DataFrame,
            "embeddings_u": pd.DataFrame,          # microbe × latent_dim
            "embeddings_v": pd.DataFrame,          # metabolite × latent_dim
            "biplot": plotly JSON,
            "training_stats": {
                "engine": str,
                "final_train_loss": float,
                "final_val_loss": float,
                "epochs_trained": int,
            },
        }
    """
    if microbiome_df.empty or metabolome_df.empty:
        raise ValueError("microbiome_df and metabolome_df must be non-empty.")

    common_samples = microbiome_df.index.intersection(metabolome_df.index)
    if len(common_samples) == 0:
        raise ValueError(
            "No common samples between microbiome and metabolome data."
        )

    mb = microbiome_df.loc[common_samples].copy()
    mt = metabolome_df.loc[common_samples].copy()

    n_samples = len(common_samples)
    n_microbes = mb.shape[1]
    n_metabolites = mt.shape[1]

    logger.info(
        f"mmvec start: n_samples={n_samples}, n_microbes={n_microbes}, "
        f"n_metabolites={n_metabolites}, latent_dim={latent_dim}"
    )

    # Pre-processing
    mb_clr = _clr_transform(mb)
    mt_log = _log_transform(mt)

    X_mb = mb_clr.values.astype(np.float32)
    Y_mt = mt_log.values.astype(np.float32)

    # Clamp latent_dim
    latent_dim = min(latent_dim, n_microbes, n_metabolites, n_samples)
    if latent_dim < 1:
        latent_dim = 1

    # ── Engine selection ────────────────────────────────────────────────
    if TORCH_AVAILABLE:
        logger.info("Running mmvec with PyTorch engine.")
        result = _train_mmvec_torch(
            X_mb, Y_mt, latent_dim=latent_dim, epochs=epochs, learning_rate=learning_rate
        )
        engine = "PyTorch"
        final_train_loss = float(result["loss_history"][-1]) if result["loss_history"] else np.nan
        final_val_loss = float(result["val_loss_history"][-1]) if result["val_loss_history"] else np.nan
        epochs_trained = len(result["loss_history"])
    else:
        logger.info("Running mmvec with NumPy SVD fallback.")
        result = _mmvec_numpy_fallback(X_mb, Y_mt, latent_dim=latent_dim)
        engine = "NumPy::SVD"
        final_train_loss = np.nan
        final_val_loss = np.nan
        epochs_trained = 0

    U = result["U"]
    V = result["V"]
    cond_prob = result["conditional_prob"]

    # DataFrames
    embeddings_u = pd.DataFrame(
        U,
        index=mb.columns,
        columns=[f"Dim{i + 1}" for i in range(U.shape[1])],
    )
    embeddings_v = pd.DataFrame(
        V,
        index=mt.columns,
        columns=[f"Dim{i + 1}" for i in range(V.shape[1])],
    )
    cond_prob_df = pd.DataFrame(
        cond_prob,
        index=common_samples,
        columns=mt.columns,
    )

    # Biplot
    biplot = _build_biplot(U, V, mb.columns, mt.columns)

    logger.info("mmvec complete.")

    return {
        "conditional_prob_matrix": cond_prob_df,
        "embeddings_u": embeddings_u,
        "embeddings_v": embeddings_v,
        "biplot": biplot,
        "training_stats": {
            "engine": engine,
            "final_train_loss": final_train_loss,
            "final_val_loss": final_val_loss,
            "epochs_trained": epochs_trained,
            "latent_dim": int(latent_dim),
            "n_samples": int(n_samples),
            "n_microbes": int(n_microbes),
            "n_metabolites": int(n_metabolites),
        },
    }
