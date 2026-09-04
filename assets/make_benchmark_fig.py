"""Nature-style grouped bar chart: Minta vs competitors on Memory Quality metrics."""
import os

import matplotlib.pyplot as plt
import numpy as np

# ── Nature + User rcParams ──
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['svg.fonttype'] = 'none'
plt.rcParams['font.size'] = 12
plt.rcParams['axes.spines.right'] = False
plt.rcParams['axes.spines.top'] = False
plt.rcParams['axes.linewidth'] = 1.5
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.15
# grid.axis not in older mpl; use manual y-grid later
plt.rcParams['legend.frameon'] = True
plt.rcParams['legend.framealpha'] = 0.8
plt.rcParams['figure.dpi'] = 120
plt.rcParams['savefig.dpi'] = 300

# ── Data ──
systems = ['Minta', 'Mem0', 'Zep', 'Hindsight']
metrics = ['Evidence\nRecall@20', 'Conflict\nF1', 'Staleness\nUFA']

# [system][metric]: None = N/A
data = {
    'Minta':     [82.6, 0.81, 0.86],
    'Mem0':      [66.9, None, None],
    'Zep':       [75.1, None, None],
    'Hindsight': [89.6, None, None],
}

# Normalize: Ev@20 is %, Conflict F1 and UFA are 0-1
# Show Ev@20 as-is (%), Conflict and UFA as percentage-like (×100 for visual scale)
plot_data = {}
for sys_name, vals in data.items():
    row = []
    for i, v in enumerate(vals):
        if v is None:
            row.append(0)
        elif i == 0:
            row.append(v)         # Ev@20 already in %
        else:
            row.append(v * 100)   # F1/UFA scaled to 0-100 for visual
    plot_data[sys_name] = row

# ── Colors ──
MINTA_PURPLE = '#6366f1'
GRAY = '#b0b0b0'
GRAY_LIGHT = '#d8d8d8'
colors = [MINTA_PURPLE, GRAY, GRAY_LIGHT, '#e8e8e8']

# ── Figure ──
fig, ax = plt.subplots(figsize=(8, 5))

x = np.arange(len(metrics))
width = 0.18
offset = [-1.5, -0.5, 0.5, 1.5]  # centered groups

bars = []
for i, (sys_name, offset_i) in enumerate(zip(systems, offset)):
    vals = plot_data[sys_name]
    bar = ax.bar(
        x + offset_i * width,
        vals,
        width * 0.85,
        label=sys_name,
        color=colors[i],
        edgecolor='white' if i == 0 else 'none',
        linewidth=0.5 if i == 0 else 0,
        zorder=3 if i == 0 else 2,
    )
    bars.append(bar)

    # Value labels on Minta bars only
    if sys_name == 'Minta':
        for j, (bar_patch, orig_val) in enumerate(zip(bar, data[sys_name])):
            if orig_val is not None:
                val_text = f'{orig_val:.0f}%' if j == 0 else f'{orig_val:.2f}'
                ax.text(
                    bar_patch.get_x() + bar_patch.get_width() / 2,
                    bar_patch.get_height() + 1.5,
                    val_text,
                    ha='center', va='bottom',
                    fontsize=9, fontweight='bold',
                    color=MINTA_PURPLE,
                )

# ── N/A annotations for missing metrics ──
na_positions = [
    (1, 'Mem0'), (2, 'Mem0'),
    (1, 'Zep'), (2, 'Zep'),
    (1, 'Hindsight'), (2, 'Hindsight'),
]
sys_idx = {'Mem0': 1, 'Zep': 2, 'Hindsight': 3}
metric_offset = {1: -0.5, 2: 0.5, 3: 1.5}
for met_idx, sys_name in na_positions:
    pos_x = x[met_idx] + metric_offset[sys_idx[sys_name]] * width
    ax.text(
        pos_x, 1.5, 'N/A',
        ha='center', va='bottom',
        fontsize=7, color='#999', fontstyle='italic',
    )

# ── Labels ──
ax.set_xticks(x)
ax.set_xticklabels(metrics)
ax.set_ylabel('Score (%)')
ax.set_ylim(0, 105)

# ── Legend ──
ax.legend(loc='upper left', fontsize=10, ncol=4,
          columnspacing=0.8, handletextpad=0.5)

# ── Title ──
ax.set_title(
    'Memory Quality: Minta Is the Only System\n'
    'That Measures Conflict and Staleness',
    fontsize=14, fontweight='bold', color='#333', pad=16,
)

# ── Annotation ──
ax.annotate(
    'Only Minta measures\nwhat others ignore',
    xy=(1.5, 81),
    fontsize=9, color=MINTA_PURPLE, fontstyle='italic',
    ha='left',
    bbox=dict(boxstyle='round,pad=0.3', facecolor='#f0edff',
              edgecolor=MINTA_PURPLE, alpha=0.6),
)

# ── Source note ──
fig.text(
    0.5, -0.02,
    'Ev@20 from LoCoMo benchmark. Conflict F1 and Staleness UFA from held-out evaluation.\n'
    'Mem0, Zep, and Hindsight do not report conflict or staleness metrics.',
    ha='center', fontsize=7, color='#999', fontstyle='italic',
)

plt.tight_layout()

# ── Export ──
# Output goes next to the script (repo assets dir) by default; the arg is
# `--out` for anywhere else. Never hardcode a machine-specific path.
out_base = os.environ.get(
    "MINT_BENCH_FIG_OUT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_comparison"))
plt.savefig(out_base + '.pdf', bbox_inches='tight')
plt.savefig(out_base + '.png', dpi=300, bbox_inches='tight')
print(f'Saved: {out_base}.pdf + .png')
plt.close()
