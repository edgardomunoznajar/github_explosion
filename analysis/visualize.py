"""
Step 5: Visualization module.

Generates publication-quality plots for the GitHub Explosion analysis.
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    ANNOTATION_COLOR,
    CHATGPT_LAUNCH,
    COLOR_POST_AI,
    COLOR_PRE_AI,
    COPILOT_GA,
    DATA_DIR,
    FIGURE_DPI,
    FIGURE_SIZE,
    VIZ_DIR,
)


def plot_push_velocity_timeseries(
    df: pd.DataFrame,
    breakpoints: list[str] | None = None,
    output_path: Path | None = None,
) -> None:
    """
    Plot per-developer push velocity over time with breakpoint annotations.
    """
    if output_path is None:
        output_path = VIZ_DIR / "push_velocity_timeseries.png"

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)

    chatgpt_date = pd.Timestamp(CHATGPT_LAUNCH + "-01")

    # Color-code pre/post AI
    pre_mask = df["date"] < chatgpt_date
    post_mask = df["date"] >= chatgpt_date

    ax.plot(
        df.loc[pre_mask, "date"], df.loc[pre_mask, "pushes_per_dev"],
        color=COLOR_PRE_AI, linewidth=2, label="Pre-ChatGPT",
    )
    ax.plot(
        df.loc[post_mask, "date"], df.loc[post_mask, "pushes_per_dev"],
        color=COLOR_POST_AI, linewidth=2, label="Post-ChatGPT",
    )

    # Mark key dates
    ax.axvline(chatgpt_date, color=ANNOTATION_COLOR, linestyle="--", alpha=0.7, linewidth=1.5)
    ax.annotate(
        "ChatGPT\nLaunch",
        xy=(chatgpt_date, ax.get_ylim()[1]),
        xytext=(10, -20), textcoords="offset points",
        fontsize=9, color=ANNOTATION_COLOR, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=ANNOTATION_COLOR),
    )

    copilot_date = pd.Timestamp(COPILOT_GA + "-01")
    ax.axvline(copilot_date, color=ANNOTATION_COLOR, linestyle=":", alpha=0.5)
    ax.annotate(
        "Copilot GA",
        xy=(copilot_date, ax.get_ylim()[0]),
        xytext=(10, 20), textcoords="offset points",
        fontsize=8, color=ANNOTATION_COLOR, alpha=0.7,
    )

    # Mark detected breakpoints
    if breakpoints:
        for bp_date in breakpoints:
            bp = pd.Timestamp(bp_date + "-01")
            ax.axvline(bp, color="#4CAF50", linestyle="-.", alpha=0.6)
            ax.annotate(
                f"Breakpoint\n{bp_date}",
                xy=(bp, df["pushes_per_dev"].max()),
                xytext=(10, -30), textcoords="offset points",
                fontsize=8, color="#4CAF50",
            )

    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Pushes per Developer (monthly)", fontsize=12)
    ax.set_title("Per-Developer Push Velocity on GitHub (2020-2025)", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    fig.autofmt_xdate()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path}")


def plot_commit_size_distribution(
    df: pd.DataFrame,
    output_path: Path | None = None,
) -> None:
    """
    Plot commit size metrics over time (avg, median, percentiles).
    """
    if output_path is None:
        output_path = VIZ_DIR / "commit_size_distribution.png"

    fig, axes = plt.subplots(1, 2, figsize=FIGURE_SIZE)

    chatgpt_quarter = pd.Timestamp(CHATGPT_LAUNCH + "-01")

    # Left: averages and medians
    ax = axes[0]
    ax.plot(df["date"], df["avg_commits_per_push"], "o-", color=COLOR_PRE_AI, label="Mean", linewidth=2)
    if "median_commits_per_push" in df.columns:
        ax.plot(df["date"], df["median_commits_per_push"], "s-", color=COLOR_POST_AI, label="Median", linewidth=2)
    ax.axvline(chatgpt_quarter, color=ANNOTATION_COLOR, linestyle="--", alpha=0.7)
    ax.set_title("Commits per Push: Central Tendency", fontweight="bold")
    ax.set_xlabel("Quarter")
    ax.set_ylabel("Commits per Push")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Right: percentile range (IQR)
    ax = axes[1]
    if all(col in df.columns for col in ["p25_commits_per_push", "p75_commits_per_push"]):
        ax.fill_between(
            df["date"], df["p25_commits_per_push"], df["p75_commits_per_push"],
            alpha=0.3, color=COLOR_PRE_AI, label="IQR (P25-P75)",
        )
    if "p95_commits_per_push" in df.columns:
        ax.plot(df["date"], df["p95_commits_per_push"], "--", color=COLOR_POST_AI, label="P95", linewidth=1.5)
    if "median_commits_per_push" in df.columns:
        ax.plot(df["date"], df["median_commits_per_push"], "-", color=COLOR_PRE_AI, label="Median", linewidth=2)
    ax.axvline(chatgpt_quarter, color=ANNOTATION_COLOR, linestyle="--", alpha=0.7)
    ax.set_title("Commits per Push: Distribution", fontweight="bold")
    ax.set_xlabel("Quarter")
    ax.set_ylabel("Commits per Push")
    ax.legend()
    ax.grid(True, alpha=0.3)

    fig.suptitle("Commit Size Distribution Over Time", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path}")


def plot_text_feature_comparison(
    results: dict,
    output_path: Path | None = None,
) -> None:
    """
    Bar chart comparing text features between pre- and post-AI eras.
    """
    if output_path is None:
        output_path = VIZ_DIR / "text_feature_comparison.png"

    features = list(results.keys())
    pre_vals = [results[f]["pre_mean"] for f in features]
    post_vals = [results[f]["post_mean"] for f in features]
    significant = [results[f]["significant"] for f in features]

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)

    x = np.arange(len(features))
    width = 0.35

    bars_pre = ax.bar(x - width / 2, pre_vals, width, label="Pre-AI (2021)", color=COLOR_PRE_AI, alpha=0.8)
    bars_post = ax.bar(x + width / 2, post_vals, width, label="Post-AI (2024)", color=COLOR_POST_AI, alpha=0.8)

    # Mark significant differences
    for i, sig in enumerate(significant):
        if sig:
            max_val = max(pre_vals[i], post_vals[i])
            ax.annotate("*", xy=(x[i], max_val), fontsize=16, ha="center", fontweight="bold")

    ax.set_xlabel("Feature", fontsize=12)
    ax.set_ylabel("Mean Value", fontsize=12)
    ax.set_title("Commit Message Features: Pre-AI vs Post-AI", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(features, rotation=45, ha="right", fontsize=9)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path}")


def plot_yoy_growth(
    df: pd.DataFrame,
    output_path: Path | None = None,
) -> None:
    """
    Year-over-year growth rates for pushes, unique pushers, and velocity.
    """
    if output_path is None:
        output_path = VIZ_DIR / "yoy_growth.png"

    # Compute annual aggregates
    annual = df.groupby(df["date"].dt.year).agg({
        "total_pushes": "sum",
        "unique_pushers": "mean",
        "pushes_per_dev": "mean",
    }).reset_index()
    annual.columns = ["year", "total_pushes", "avg_unique_pushers", "avg_pushes_per_dev"]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    metrics = [
        ("total_pushes", "Total Pushes", COLOR_PRE_AI),
        ("avg_unique_pushers", "Avg Unique Pushers/Month", COLOR_POST_AI),
        ("avg_pushes_per_dev", "Avg Pushes per Developer", "#4CAF50"),
    ]

    for ax, (col, title, color) in zip(axes, metrics):
        vals = annual[col].values
        yoy = [(vals[i] - vals[i - 1]) / vals[i - 1] * 100 for i in range(1, len(vals))]
        years = annual["year"].values[1:]

        bars = ax.bar(years, yoy, color=color, alpha=0.8)

        # Color bars differently pre/post ChatGPT
        for bar, year in zip(bars, years):
            if year <= 2022:
                bar.set_alpha(0.5)

        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel("Year")
        ax.set_ylabel("YoY Growth (%)")
        ax.grid(True, alpha=0.3, axis="y")

        # Annotate values
        for bar, val in zip(bars, yoy):
            ax.text(
                bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{val:+.1f}%", ha="center", va="bottom", fontsize=9,
            )

    fig.suptitle("Year-over-Year Growth Rates", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path}")


def generate_all_plots() -> None:
    """Generate all visualizations from available data."""
    from analysis.changepoint import load_push_velocity, analyse as changepoint_analyse
    from analysis.commit_size import load_commit_size_data

    # Push velocity plot
    velocity_file = DATA_DIR / "monthly_pushes_per_dev.csv"
    if velocity_file.exists():
        df = load_push_velocity()
        cp_results = changepoint_analyse()
        breakpoints = cp_results["breakpoints"]["dates"]
        plot_push_velocity_timeseries(df, breakpoints)
        plot_yoy_growth(df)
    else:
        print(f"Skipping velocity plots: {velocity_file} not found")

    # Commit size plot
    size_file = DATA_DIR / "commit_size_distribution.csv"
    if size_file.exists():
        df = load_commit_size_data()
        plot_commit_size_distribution(df)
    else:
        print(f"Skipping commit size plots: {size_file} not found")

    # Text feature plot
    pre_file = DATA_DIR / "commit_messages_pre_ai.csv"
    post_file = DATA_DIR / "commit_messages_post_ai.csv"
    if pre_file.exists() and post_file.exists():
        from analysis.nlp_pipeline import analyse_text_features
        text_results = analyse_text_features()
        plot_text_feature_comparison(text_results)
    else:
        print(f"Skipping NLP plots: commit message CSVs not found")


if __name__ == "__main__":
    generate_all_plots()
