#!/usr/bin/env python3
"""Fix Procrustes plot and add standalone metabolome PCoA."""
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.spatial.distance import braycurtis, pdist, squareform
from scipy.stats import pearsonr
from scipy.linalg import orthogonal_procrustes
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("husl")

out = '/Users/shihuang/Documents/kimi/workspace/meta2banalyst'

# ── Load data ──────────────────────────────────────────
microbes = pd.read_csv('/Users/shihuang/MyProjects/SoH_project/multi-omics/Matched_microbes_genus.abd_261.txt', sep='\t', index_col=0).T
metabolites = pd.read_csv('/Users/shihuang/MyProjects/SoH_project/multi-omics/Matched_metabolites_abd_261.txt', sep='\t', index_col=0).T
meta = pd.read_csv('/Users/shihuang/MyProjects/SoH_project/multi-omics/Matched_microbes_metadata_261.txt', sep='\t', index_col=0)

common = microbes.columns.intersection(metabolites.columns)
microbes = microbes[common]
metabolites = metabolites[common]
meta = meta.loc[common]

visits = meta['Visit']
visit_colors = {v: plt.cm.tab10(i) for i, v in enumerate(sorted(visits.unique()))}

print(f"Samples: {len(common)}")

# ── Microbiome PCoA (Bray-Curtis) ──────────────────────
dist_mb = squareform(pdist(microbes.T.values, metric='braycurtis'))
n = len(common)
H = np.eye(n) - np.ones((n, n)) / n
B = -0.5 * H @ (dist_mb ** 2) @ H
eigvals, eigvecs = np.linalg.eigh(B)
idx = np.argsort(eigvals)[::-1]
eigvals = eigvals[idx]
eigvecs = eigvecs[:, idx]
pos_idx = eigvals > 0
coords_mb = eigvecs[:, pos_idx] * np.sqrt(eigvals[pos_idx])
var_mb = (eigvals[pos_idx] / eigvals[pos_idx].sum()) * 100

# ── Metabolome PCoA (Bray-Curtis) ──────────────────────
# For metabolites, use Bray-Curtis on normalized data
metabolites_norm = metabolites.div(metabolites.sum(axis=0), axis=1)
metabolites_norm = metabolites_norm.fillna(0)
dist_met_bc = squareform(pdist(metabolites_norm.T.values, metric='braycurtis'))
B_met = -0.5 * H @ (dist_met_bc ** 2) @ H
eigvals_met, eigvecs_met = np.linalg.eigh(B_met)
idx_met = np.argsort(eigvals_met)[::-1]
eigvals_met = eigvals_met[idx_met]
eigvecs_met = eigvecs_met[:, idx_met]
pos_idx_met = eigvals_met > 0
coords_met_pcoa = eigvecs_met[:, pos_idx_met] * np.sqrt(eigvals_met[pos_idx_met])
var_met_pcoa = (eigvals_met[pos_idx_met] / eigvals_met[pos_idx_met].sum()) * 100

# ── Metabolome PCA (standardized) ──────────────────────
met_std = StandardScaler().fit_transform(metabolites.T.values)
pca_met = PCA(n_components=10)
pca_coords = pca_met.fit_transform(met_std)
met_var = pca_met.explained_variance_ratio_ * 100

# ── Procrustes: Align metabolome PCA to microbiome PCoA ─
# Use first 2 dimensions of both
X = coords_mb[:, :2]  # Microbiome PCoA (reference)
Y = pca_coords[:, :2]  # Metabolome PCA (to align)

# Center both
X_centered = X - X.mean(axis=0)
Y_centered = Y - Y.mean(axis=0)

# Orthogonal Procrustes: find R that minimizes ||XR - Y||_F
R, s = orthogonal_procrustes(Y_centered, X_centered)
Y_aligned = Y_centered @ R + X.mean(axis=0)

# Compute m2
m2 = np.sum((X - Y_aligned) ** 2)
norm_m2 = m2 / np.sum((X - X.mean(axis=0)) ** 2)

print(f"Procrustes: m2={m2:.4f}, norm_m2={norm_m2:.6f}, scale={s:.3f}")

# Mantel test
idx_triu = np.triu_indices(n, k=1)
mantel_r, mantel_p = pearsonr(dist_mb[idx_triu], dist_met_bc[idx_triu])
print(f"Mantel: r={mantel_r:.3f}, p={mantel_p:.4f}")

# ── FIGURE 1: Fixed Procrustes with both points visible ──
fig, axes = plt.subplots(1, 2, figsize=(16, 7))

# Left panel: Microbiome PCoA
for v in sorted(visits.unique()):
    mask = visits == v
    axes[0].scatter(X[mask, 0], X[mask, 1], 
                   c=[visit_colors[v]], label=v, s=50, alpha=0.7, edgecolors='black', linewidth=0.3)
axes[0].set_xlabel(f'PCoA1 ({var_mb[0]:.1f}%)', fontsize=11)
axes[0].set_ylabel(f'PCoA2 ({var_mb[1]:.1f}%)', fontsize=11)
axes[0].set_title('A. Microbiome PCoA (Bray-Curtis)', fontsize=13, fontweight='bold')
axes[0].legend(title='Visit', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=8)

# Right panel: Procrustes with BOTH points and connecting lines
ax = axes[1]

# Plot microbiome points (circles) - reference
for v in sorted(visits.unique()):
    mask = visits == v
    ax.scatter(X[mask, 0], X[mask, 1], 
              c=[visit_colors[v]], s=60, alpha=0.6, 
              marker='o', edgecolors='black', linewidth=0.5,
              zorder=3)

# Plot metabolome points (triangles) - aligned
for v in sorted(visits.unique()):
    mask = visits == v
    ax.scatter(Y_aligned[mask, 0], Y_aligned[mask, 1], 
              c=[visit_colors[v]], s=60, alpha=0.6, 
              marker='^', edgecolors='black', linewidth=0.5,
              zorder=3)

# Add connecting lines between paired samples
for i in range(n):
    ax.plot([X[i, 0], Y_aligned[i, 0]], 
           [X[i, 1], Y_aligned[i, 1]], 
           'k-', alpha=0.15, linewidth=0.4, zorder=1)

# Add legend
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor='gray', markersize=10, 
           label='Microbiome', markeredgecolor='black'),
    Line2D([0], [0], marker='^', color='w', markerfacecolor='gray', markersize=10, 
           label='Metabolome (aligned)', markeredgecolor='black'),
]
ax.legend(handles=legend_elements, loc='upper left', fontsize=10)

ax.set_xlabel('PCoA1 / PC1', fontsize=11)
ax.set_ylabel('PCoA2 / PC2', fontsize=11)
ax.set_title(f'B. Procrustes Alignment\nm²={norm_m2:.4f}, scale={s:.2f}', fontsize=13, fontweight='bold')

plt.suptitle('Microbiome-Metabolome Procrustes Analysis', fontsize=15, y=1.02)
plt.tight_layout()
plt.savefig(f'{out}/multiomics_fig1_procrustes_fixed.png', dpi=200, bbox_inches='tight')
plt.close()
print("  Fig 1: Procrustes fixed - both circles AND triangles visible")

# ── FIGURE 2: Standalone Metabolome PCoA ─────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Left: Metabolome PCoA (Bray-Curtis)
for v in sorted(visits.unique()):
    mask = visits == v
    axes[0].scatter(coords_met_pcoa[mask, 0], coords_met_pcoa[mask, 1], 
                   c=[visit_colors[v]], label=v, s=50, alpha=0.7, edgecolors='black', linewidth=0.3)
axes[0].set_xlabel(f'PCoA1 ({var_met_pcoa[0]:.1f}%)', fontsize=11)
axes[0].set_ylabel(f'PCoA2 ({var_met_pcoa[1]:.1f}%)', fontsize=11)
axes[0].set_title('A. Metabolome PCoA (Bray-Curtis)', fontsize=13, fontweight='bold')
axes[0].legend(title='Visit', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=8)

# Right: Metabolome PCA (standardized)
for v in sorted(visits.unique()):
    mask = visits == v
    axes[1].scatter(pca_coords[mask, 0], pca_coords[mask, 1], 
                   c=[visit_colors[v]], label=v, s=50, alpha=0.7, edgecolors='black', linewidth=0.3)
axes[1].set_xlabel(f'PC1 ({met_var[0]:.1f}%)', fontsize=11)
axes[1].set_ylabel(f'PC2 ({met_var[1]:.1f}%)', fontsize=11)
axes[1].set_title('B. Metabolome PCA (Standardized)', fontsize=13, fontweight='bold')
axes[1].legend(title='Visit', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=8)

plt.suptitle('Metabolome Ordination Analysis', fontsize=15, y=1.02)
plt.tight_layout()
plt.savefig(f'{out}/multiomics_fig2_metabolome_ordination.png', dpi=200, bbox_inches='tight')
plt.close()
print("  Fig 2: Metabolome PCoA + PCA created")

# ── FIGURE 3: Side-by-side comparison with links ─────────
fig, axes = plt.subplots(1, 3, figsize=(20, 6))

# Panel A: Microbiome PCoA
for v in sorted(visits.unique()):
    mask = visits == v
    axes[0].scatter(X[mask, 0], X[mask, 1], 
                   c=[visit_colors[v]], label=v, s=50, alpha=0.8, edgecolors='black', linewidth=0.3)
axes[0].set_xlabel(f'PCoA1 ({var_mb[0]:.1f}%)', fontsize=11)
axes[0].set_ylabel(f'PCoA2 ({var_mb[1]:.1f}%)', fontsize=11)
axes[0].set_title('A. Microbiome PCoA', fontsize=13, fontweight='bold')
axes[0].legend(title='Visit', fontsize=8)

# Panel B: Metabolome PCoA
for v in sorted(visits.unique()):
    mask = visits == v
    axes[1].scatter(coords_met_pcoa[mask, 0], coords_met_pcoa[mask, 1], 
                   c=[visit_colors[v]], label=v, s=50, alpha=0.8, edgecolors='black', linewidth=0.3)
axes[1].set_xlabel(f'PCoA1 ({var_met_pcoa[0]:.1f}%)', fontsize=11)
axes[1].set_ylabel(f'PCoA2 ({var_met_pcoa[1]:.1f}%)', fontsize=11)
axes[1].set_title('B. Metabolome PCoA', fontsize=13, fontweight='bold')
axes[1].legend(title='Visit', fontsize=8)

# Panel C: Procrustes with links
ax3 = axes[2]
for v in sorted(visits.unique()):
    mask = visits == v
    ax3.scatter(X[mask, 0], X[mask, 1], 
               c=[visit_colors[v]], s=50, alpha=0.6, 
               marker='o', edgecolors='black', linewidth=0.5, zorder=3)
    ax3.scatter(Y_aligned[mask, 0], Y_aligned[mask, 1], 
               c=[visit_colors[v]], s=50, alpha=0.6, 
               marker='^', edgecolors='black', linewidth=0.5, zorder=3)

# Add connecting lines for ALL samples
for i in range(n):
    ax3.plot([X[i, 0], Y_aligned[i, 0]], 
            [X[i, 1], Y_aligned[i, 1]], 
            'k-', alpha=0.12, linewidth=0.3, zorder=1)

ax3.legend(handles=legend_elements, loc='upper left', fontsize=9)
ax3.set_xlabel('Aligned Axis 1', fontsize=11)
ax3.set_ylabel('Aligned Axis 2', fontsize=11)
ax3.set_title(f'C. Procrustes Alignment\n(m²={norm_m2:.4f}, r={mantel_r:.3f})', fontsize=13, fontweight='bold')

plt.suptitle('Microbiome-Metabolome Multi-omics Integration', fontsize=15, y=1.02)
plt.tight_layout()
plt.savefig(f'{out}/multiomics_fig3_three_panel.png', dpi=200, bbox_inches='tight')
plt.close()
print("  Fig 3: Three-panel comparison with links created")

# ── FIGURE 4: Mantel Test (unchanged but higher quality) ─
fig, ax = plt.subplots(figsize=(9, 8))
ax.scatter(dist_mb[idx_triu], dist_met_bc[idx_triu], alpha=0.15, s=4, c='darkgreen', edgecolors='none')
z = np.polyfit(dist_mb[idx_triu], dist_met_bc[idx_triu], 1)
p_line = np.poly1d(z)
x_line = np.linspace(dist_mb[idx_triu].min(), dist_mb[idx_triu].max(), 100)
ax.plot(x_line, p_line(x_line), 'r--', lw=2.5, label=f'r={mantel_r:.3f}, p={mantel_p:.4f}')
ax.set_xlabel('Microbiome Bray-Curtis Distance', fontsize=12)
ax.set_ylabel('Metabolome Bray-Curtis Distance', fontsize=12)
ax.set_title('Mantel Test: Distance Matrix Correlation', fontsize=14, fontweight='bold')
ax.legend(fontsize=12)
plt.tight_layout()
plt.savefig(f'{out}/multiomics_fig4_mantel.png', dpi=200, bbox_inches='tight')
plt.close()
print("  Fig 4: Mantel test updated")

print("\n✅ All figures fixed and generated!")
