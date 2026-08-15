import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# Set up the figure with poster-friendly dimensions
fig, ax = plt.subplots(1, 1, figsize=(16, 10), dpi=150)
ax.set_xlim(0, 16)
ax.set_ylim(0, 10)
ax.axis('off')

# Color scheme - low saturation, warm tones
colors = {
    'upload': '#E8D5C4',      # warm beige
    'qc': '#D4C4B0',          # light taupe
    'filter': '#C9B8A3',      # warm gray
    'normalize': '#B8C9A9',   # sage green
    'analysis': '#A3B8C9',    # soft blue
    'viz': '#C9A3B8',         # muted rose
    'agent': '#F4E4C1',       # warm cream
    'sub': '#E8E0D5',         # light neutral
    'arrow': '#8B7355',       # warm brown
    'text': '#4A4A4A',        # dark gray
    'title': '#2C2C2C',       # near black
}

def draw_box(ax, x, y, w, h, text, color, fontsize=11, text_color='#4A4A4A', radius=0.08):
    """Draw a rounded rectangle with text."""
    box = FancyBboxPatch((x - w/2, y - h/2), w, h,
                         boxstyle=f"round,pad=0.02,rounding_size={radius}",
                         facecolor=color, edgecolor='#999999', linewidth=1.2,
                         zorder=2)
    ax.add_patch(box)
    ax.text(x, y, text, ha='center', va='center', fontsize=fontsize,
            color=text_color, fontweight='bold', zorder=3)
    return box

def draw_arrow(ax, x1, y1, x2, y2, color='#8B7355'):
    """Draw an arrow between two points."""
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=2,
                              connectionstyle='arc3,rad=0'),
                zorder=1)

def draw_small_box(ax, x, y, w, h, text, color, fontsize=9):
    """Draw smaller sub-step box."""
    box = FancyBboxPatch((x - w/2, y - h/2), w, h,
                         boxstyle="round,pad=0.02,rounding_size=0.05",
                         facecolor=color, edgecolor='#AAAAAA', linewidth=1,
                         zorder=2)
    ax.add_patch(box)
    ax.text(x, y, text, ha='center', va='center', fontsize=fontsize,
            color='#555555', zorder=3)

# Title
ax.text(8, 9.5, 'Meta2bAnalyst: Analysis Workflow', ha='center', va='center',
        fontsize=22, fontweight='bold', color=colors['title'])
ax.text(8, 9.1, 'From Raw Data to AI-Powered Interpretation', ha='center', va='center',
        fontsize=13, color='#666666', style='italic')

# Main workflow - horizontal layout
# Y positions
main_y = 6.5
sub_y = 4.0
agent_y = 2.0

# Main steps positions
steps = [
    (1.5, 'Upload', colors['upload']),
    (3.5, 'QC &\nInspection', colors['qc']),
    (5.5, 'Filter', colors['filter']),
    (7.5, 'Normalize', colors['normalize']),
    (9.5, 'Analysis', colors['analysis']),
    (11.5, 'Visualization', colors['viz']),
    (14.0, 'AI Agent\nInterpretation', colors['agent']),
]

box_w, box_h = 1.6, 1.0

# Draw main steps
for i, (x, text, color) in enumerate(steps):
    draw_box(ax, x, main_y, box_w, box_h, text, color)

# Draw main arrows
for i in range(len(steps) - 1):
    x1, x2 = steps[i][0] + box_w/2 + 0.1, steps[i+1][0] - box_w/2 - 0.1
    draw_arrow(ax, x1, main_y, x2, main_y)

# Analysis sub-steps (under Analysis)
sub_steps = [
    (7.8, 'Alpha\nDiversity'),
    (9.5, 'Beta\nDiversity'),
    (11.2, 'LEfSe'),
    (12.8, 'PICRUSt2'),
]

# Draw sub-step boxes
for x, text in sub_steps:
    draw_small_box(ax, x, sub_y, 1.3, 0.8, text, colors['sub'])

# Arrows from Analysis to sub-steps
for x, _ in sub_steps:
    ax.annotate('', xy=(x, sub_y + 0.5), xytext=(9.5, main_y - 0.55),
                arrowprops=dict(arrowstyle='->', color='#AAAAAA', lw=1.2,
                              connectionstyle=f'arc3,rad={0.05 if x < 9.5 else -0.05}'),
                zorder=1)

# Agent capabilities (under Agent Interpretation)
agent_caps = [
    (12.5, 'Natural Language\nQueries'),
    (14.0, 'Knowledge Base\nQ&A'),
    (15.5, 'Statistical\nGuidance'),
]

for x, text in agent_caps:
    draw_small_box(ax, x, agent_y, 1.4, 0.8, text, colors['agent'], fontsize=8.5)

# Arrows from Agent to capabilities
for x, _ in agent_caps:
    ax.annotate('', xy=(x, agent_y + 0.5), xytext=(14.0, main_y - 0.55),
                arrowprops=dict(arrowstyle='->', color='#AAAAAA', lw=1.2,
                              connectionstyle=f'arc3,rad={0.08 if x < 14 else -0.08}'),
                zorder=1)

# Add feature labels on the side
feature_x = 0.6
features = [
    (6.5, '• Batch processing'),
    (6.0, '• QC reports'),
    (5.5, '• Metadata integration'),
]

# Add input/output labels
ax.text(1.5, 8.2, 'Input: FASTQ / OTU / BIOM', ha='center', va='center',
        fontsize=9, color='#888888', style='italic')
ax.text(14.0, 8.2, 'Output: Insights & Reports', ha='center', va='center',
        fontsize=9, color='#888888', style='italic')

# Add a subtle border
border = FancyBboxPatch((0.2, 0.3), 15.6, 9.4,
                        boxstyle="round,pad=0.02,rounding_size=0.15",
                        facecolor='none', edgecolor='#CCCCCC', linewidth=1.5,
                        linestyle='--', zorder=0)
ax.add_patch(border)

plt.tight_layout()
plt.savefig('/Users/shihuang/Documents/kimi/workspace/meta2banalyst/poster_workflow_diagram.png',
            dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
plt.savefig('/Users/shihuang/Documents/kimi/workspace/meta2banalyst/poster_workflow_diagram.svg',
            bbox_inches='tight', facecolor='white', edgecolor='none')
print("Diagrams saved successfully!")
