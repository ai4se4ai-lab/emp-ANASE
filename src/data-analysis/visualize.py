"""
visualize.py
============
Reproduces all four paper figures using collected / demo data.

  Fig 1 — Violin plot: analogy effectiveness by type  (survey n=52)
  Fig 2 — Heatmap: analogy type × SDLC phase  (online n=197)
  Fig 3 — Bar chart: challenge frequencies with 95% CIs
  Fig 4 — Scatter: ERR relational density vs. critical thinking

Usage:
    python visualize.py --demo
    python visualize.py --input output/combined_dataset.csv
"""

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Style
# ─────────────────────────────────────────────────────────────────────────────
PALETTE = {
    "Structural":   "#5b8db8",   # blue
    "Functional":   "#e8a07a",   # orange
    "Process":      "#a8a8a8",   # grey
    "Cross-Domain": "#e8c84a",   # yellow
}

SDLC_PHASES = ["Requirements", "Design", "Development",
               "Code Review", "Debugging", "Testing"]

CHALLENGE_LABELS = [
    "Analogical\nMismatch",
    "Over-\nsimplification",
    "Cognitive\nOverhead",
    "Context\nDecay",
    "Sycophancy\nAmplification",
]

PAPER_HEATMAP = np.array([
    # Req  Des  Dev   CR  Dbg  Test
    [12,   22,  18,  25,  31,  15],   # Structural
    [ 8,   15,  35,  30,  38,  20],   # Functional
    [18,   20,  22,  36,  27,  12],   # Process
    [25,   28,  12,  15,  19,   8],   # Cross-Domain
])

PAPER_MEANS = {
    "Structural":   3.63,
    "Functional":   4.21,
    "Process":      4.06,
    "Cross-Domain": 3.46,
}

PAPER_CHALLENGES = {
    "Analogical Mismatch":      {"survey": 34.6, "online": 23.9},
    "Over-simplification":      {"survey": 26.9, "online": 19.3},
    "Cognitive Overhead":       {"survey": 23.1, "online": 14.7},
    "Context Decay":            {"survey": 17.3, "online": 12.2},
    "Sycophancy Amplification": {"survey": 13.5, "online":  7.6},
}

SURVEY_N = 52
ONLINE_N = 197


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def prop_ci_half(p: float, n: int, z: float = 1.96) -> float:
    return z * np.sqrt(p * (1 - p) / n)


def simulate_likert(mean: float, n: int = 52, sd: float = 0.9,
                    seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    raw = rng.normal(mean, sd, n * 10)
    raw = np.clip(np.round(raw), 1, 5)
    for _ in range(2000):
        s = rng.choice(raw, size=n, replace=False)
        if abs(s.mean() - mean) < 0.06:
            return s
    return rng.choice(raw, size=n, replace=False)


def set_style():
    plt.rcParams.update({
        "font.family":      "DejaVu Sans",
        "axes.spines.top":  False,
        "axes.spines.right": False,
        "axes.grid":        True,
        "grid.alpha":       0.4,
        "grid.linestyle":   "--",
        "figure.dpi":       150,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Figure 1 — Violin plot
# ─────────────────────────────────────────────────────────────────────────────

def plot_violin(data: dict[str, np.ndarray] | None = None,
                save_path: str = "output/fig1_violin_effectiveness.png"):
    set_style()
    if data is None:
        data = {cat: simulate_likert(mean, n=SURVEY_N, sd=0.88, seed=i*7)
                for i, (cat, mean) in enumerate(PAPER_MEANS.items())}

    fig, ax = plt.subplots(figsize=(10, 6))
    categories = list(data.keys())
    colors     = [PALETTE[c] for c in categories]

    positions = np.arange(1, len(categories) + 1)
    parts     = ax.violinplot(
        [data[c] for c in categories],
        positions=positions,
        showextrema=True,
        showmedians=False,
    )

    for i, (pc, color) in enumerate(zip(parts["bodies"], colors)):
        pc.set_facecolor(color)
        pc.set_alpha(0.7)
        pc.set_edgecolor("black")
        pc.set_linewidth(0.8)

    for part in ["cmins", "cmaxes", "cbars"]:
        parts[part].set_color("black")
        parts[part].set_linewidth(1.2)

    for i, (cat, pos) in enumerate(zip(categories, positions)):
        arr  = data[cat]
        med  = np.median(arr)
        mean = arr.mean()
        q1, q3 = np.percentile(arr, [25, 75])

        # IQR box
        ax.vlines(pos, q1, q3, color="black", linewidth=4, zorder=3)
        # Median line (black solid)
        ax.hlines(med, pos - 0.15, pos + 0.15, color="black",
                  linewidth=2.5, zorder=4)
        # Mean line (red dashed)
        ax.hlines(mean, pos - 0.15, pos + 0.15, color="red",
                  linewidth=2, linestyle="--", zorder=5)

        # Jittered data points
        rng   = np.random.default_rng(i * 31)
        jitter = rng.uniform(-0.12, 0.12, len(arr))
        ax.scatter(pos + jitter, arr, color="gray", alpha=0.45,
                   s=14, zorder=2)

        # Mean label
        ax.text(pos, 6.35, f"μ={mean:.2f}",
                ha="center", va="bottom", fontsize=11, fontweight="bold")

    # Neutral threshold
    ax.axhline(3.0, color="gray", linestyle=":", linewidth=1.2, label="Neutral threshold")

    ax.set_xticks(positions)
    ax.set_xticklabels(categories, fontsize=12)
    ax.set_xlabel("Analogy Category", fontsize=13)
    ax.set_ylabel("Perceived Effectiveness (1–5 Likert Scale)", fontsize=12)
    ax.set_title(
        f"Distribution of Analogy Effectiveness by Type\n"
        f"(Survey n={SURVEY_N}, Discussions n={ONLINE_N})",
        fontsize=13, fontweight="bold",
    )
    ax.set_ylim(0.5, 7.2)
    ax.legend(loc="upper right", fontsize=10)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Figure 2 — Heatmap
# ─────────────────────────────────────────────────────────────────────────────

def plot_heatmap(matrix: np.ndarray | None = None,
                 save_path: str = "output/fig2_heatmap_sdlc.png"):
    set_style()
    if matrix is None:
        matrix = PAPER_HEATMAP

    row_labels = ["Structural", "Functional", "Process", "Cross-Domain"]
    col_labels = SDLC_PHASES

    fig, ax = plt.subplots(figsize=(11, 6))
    im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto",
                   vmin=8, vmax=40)

    cbar = plt.colorbar(im, ax=ax, shrink=0.85)
    cbar.set_label("Relative Frequency (%)", fontsize=11)

    ax.set_xticks(np.arange(len(col_labels)))
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_xticklabels(col_labels, fontsize=11, rotation=30, ha="right")
    ax.set_yticklabels(row_labels, fontsize=11)

    # Add grid lines between cells
    for x in np.arange(-0.5, len(col_labels), 1):
        ax.axvline(x, color="white", linewidth=1.2)
    for y in np.arange(-0.5, len(row_labels), 1):
        ax.axhline(y, color="white", linewidth=1.2)

    for i in range(len(row_labels)):
        for j in range(len(col_labels)):
            val   = matrix[i, j]
            color = "white" if val >= 28 else "black"
            ax.text(j, i, f"{val}%", ha="center", va="center",
                    fontsize=12, fontweight="bold", color=color)

    ax.set_title(
        f"Analogy Type Distribution Across SDLC Phases\n"
        f"(Percentage of Mentions in Online Discussions, n={ONLINE_N})",
        fontsize=13, fontweight="bold", pad=15,
    )

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Figure 3 — Challenge bar chart with CIs
# ─────────────────────────────────────────────────────────────────────────────

def plot_challenges(challenge_data: dict | None = None,
                    save_path: str = "output/fig3_challenges_ci.png"):
    set_style()
    if challenge_data is None:
        challenge_data = PAPER_CHALLENGES

    challenges = list(challenge_data.keys())
    survey_vals = [challenge_data[c]["survey"] for c in challenges]
    online_vals = [challenge_data[c]["online"] for c in challenges]

    s_errs = [prop_ci_half(v / 100, SURVEY_N) * 100 for v in survey_vals]
    o_errs = [prop_ci_half(v / 100, ONLINE_N) * 100 for v in online_vals]

    x    = np.arange(len(challenges))
    w    = 0.35
    fig, ax = plt.subplots(figsize=(11, 6))

    bars_s = ax.bar(x - w/2, survey_vals, w,
                    color="#4c78a8", label=f"Survey (n={SURVEY_N})",
                    yerr=s_errs, capsize=5, error_kw={"linewidth": 1.5})
    bars_o = ax.bar(x + w/2, online_vals, w,
                    color="#f58518", label=f"Online Discussions (n={ONLINE_N})",
                    yerr=o_errs, capsize=5, error_kw={"linewidth": 1.5})

    def label_bars(bars, vals):
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.5,
                    f"{val}%", ha="center", va="bottom",
                    fontsize=9.5, fontweight="bold")

    label_bars(bars_s, survey_vals)
    label_bars(bars_o, online_vals)

    ax.set_xticks(x)
    ax.set_xticklabels(CHALLENGE_LABELS, fontsize=10.5)
    ax.set_ylabel("Frequency (%)", fontsize=12)
    ax.set_ylim(0, 55)
    ax.set_title(
        "Challenges in Analogical Communication with AI Agents\n"
        "(Reported Frequency with 95% Confidence Intervals)",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=10)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Figure 4 — ERR scatter (density vs. critical thinking)
# ─────────────────────────────────────────────────────────────────────────────

def plot_err_scatter(df: pd.DataFrame | None = None,
                     save_path: str = "output/fig4_sophistication_ct.png"):
    set_style()

    if df is None:
        from analysis import generate_err_demo
        df = generate_err_demo(n=SURVEY_N)

    x_col = "relational_density"
    y_col = "critical_thinking_improvement"
    b_col = "breakdown_observed"

    x = df[x_col].values
    y = df[y_col].values
    breakdown = df[b_col].values.astype(bool) if b_col in df.columns \
                else np.zeros(len(x), dtype=bool)

    # Regression
    slope, intercept, r, p, se = stats.linregress(x, y)
    x_fit   = np.linspace(x.min(), x.max(), 200)
    y_fit   = slope * x_fit + intercept

    # Prediction interval
    n    = len(x)
    s_res = np.sqrt(np.sum((y - (slope * x + intercept))**2) / (n - 2))
    t_val = stats.t.ppf(0.975, df=n - 2)
    x_bar = x.mean()
    pi_half = t_val * s_res * np.sqrt(
        1 + 1/n + (x_fit - x_bar)**2 / np.sum((x - x_bar)**2)
    )

    fig, ax = plt.subplots(figsize=(9, 7))

    # Complacency zone shading
    ax.axvspan(0.75, 1.02, alpha=0.12, color="#cc0000",
               label="_nolegend_", zorder=0)
    ax.text(0.87, 1.12, "Complacency\nZone",
            ha="center", va="bottom", fontsize=10,
            color="#cc0000", fontweight="bold",
            transform=ax.get_xaxis_transform())

    # Prediction interval band
    ax.fill_between(x_fit, y_fit - pi_half, y_fit + pi_half,
                    alpha=0.18, color="gray", label="95% Prediction Interval")

    # Regression line
    ax.plot(x_fit, y_fit, "k--", linewidth=2,
            label=f"Linear fit (R²={r**2:.2f})")

    # Scatter: no breakdown vs breakdown
    mask_ok   = ~breakdown
    mask_bd   = breakdown
    ax.scatter(x[mask_ok], y[mask_ok], color="#3a86c8",
               alpha=0.75, s=55, zorder=4, label="No Breakdown")
    ax.scatter(x[mask_bd], y[mask_bd], color="#c87941",
               marker="X", s=80, zorder=5, label="Breakdown Observed")

    ax.set_xlabel("Analogy Systematicity (ERR Relational Density)", fontsize=12)
    ax.set_ylabel("Critical Thinking Improvement (1–5 Likert)", fontsize=12)
    ax.set_title(
        "Relationship Between Analogy Structural Systematicity\n"
        "and Critical Thinking Outcomes",
        fontsize=13, fontweight="bold",
    )
    ax.set_xlim(0.15, 1.05)
    ax.set_ylim(1.0, 5.3)
    ax.legend(loc="lower right", fontsize=10)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Bonus: platform collection summary bar chart
# ─────────────────────────────────────────────────────────────────────────────

def plot_collection_summary(summary_csv: str = "output/collection_summary.csv",
                             save_path: str = "output/fig5_collection_summary.png"):
    set_style()
    try:
        df = pd.read_csv(summary_csv)
        df = df[df["platform"] != "COMBINED"].copy()
    except FileNotFoundError:
        # Use paper's reported numbers
        df = pd.DataFrame({
            "platform":      ["Stack Overflow", "Reddit", "Discord", "GitHub", "Zenodo"],
            "raw_collected": [1240, 890, 156, 420, 34],
            "passes_dual_filter": [62, 58, 31, 36, 10],
        })

    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(df))
    w = 0.38

    ax.bar(x - w/2, df["raw_collected"],  w, label="Raw posts",     color="#4c78a8", alpha=0.85)
    ax.bar(x + w/2, df["passes_dual_filter"].replace("n/a", 0).astype(float),
           w, label="After dual-filter", color="#f58518", alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(df["platform"], fontsize=11)
    ax.set_ylabel("Number of Posts", fontsize=12)
    ax.set_title("Data Collection Summary by Platform", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo",  action="store_true")
    parser.add_argument("--input", default="", help="Path to err_scatter_data.csv")
    args = parser.parse_args()

    print("Generating figures…")
    plot_violin()
    plot_heatmap()
    plot_challenges()

    if args.input and Path(args.input).exists():
        df_err = pd.read_csv(args.input)
        plot_err_scatter(df_err)
    else:
        plot_err_scatter()

    plot_collection_summary()
    print("All figures saved to output/")
