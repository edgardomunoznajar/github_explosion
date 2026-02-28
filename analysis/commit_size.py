"""
Step 4: Commit size distribution analysis.

Detects shifts in commits-per-push over time. AI-assisted developers
tend to push larger batches less frequently — a measurable signal.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHATGPT_LAUNCH, DATA_DIR, VIZ_DIR


def load_commit_size_data(filepath: Path | None = None) -> pd.DataFrame:
    """Load commit size distribution CSV exported from BigQuery."""
    if filepath is None:
        filepath = DATA_DIR / "commit_size_distribution.csv"

    df = pd.read_csv(filepath)
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-Q" + df["quarter"].astype(str)
    )
    df = df.sort_values("date").reset_index(drop=True)
    return df


def split_by_era(df: pd.DataFrame, split_date: str = CHATGPT_LAUNCH) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split data into pre-AI and post-AI eras."""
    split = pd.Timestamp(split_date + "-01")
    return df[df["date"] < split], df[df["date"] >= split]


def analyse_distribution_shift(df: pd.DataFrame) -> dict:
    """
    Analyse how commit size distributions shifted over time.
    """
    df_pre, df_post = split_by_era(df)

    results = {}

    for metric in ["avg_commits_per_push", "median_commits_per_push"]:
        if metric not in df.columns:
            continue

        pre_vals = df_pre[metric].dropna().values
        post_vals = df_post[metric].dropna().values

        if len(pre_vals) == 0 or len(post_vals) == 0:
            continue

        # Mann-Whitney U test
        u_stat, u_pval = stats.mannwhitneyu(pre_vals, post_vals, alternative="two-sided")

        # Effect size (rank-biserial correlation)
        n1, n2 = len(pre_vals), len(post_vals)
        r_rb = 1 - (2 * u_stat) / (n1 * n2)

        results[metric] = {
            "pre_mean": float(np.mean(pre_vals)),
            "post_mean": float(np.mean(post_vals)),
            "pre_median": float(np.median(pre_vals)),
            "post_median": float(np.median(post_vals)),
            "percent_change_mean": float(
                (np.mean(post_vals) - np.mean(pre_vals)) / np.mean(pre_vals) * 100
            ),
            "mann_whitney_u": float(u_stat),
            "p_value": float(u_pval),
            "rank_biserial_r": float(r_rb),
            "significant": u_pval < 0.05,
        }

    # Trend analysis: is the metric monotonically increasing?
    if "avg_commits_per_push" in df.columns:
        tau, tau_pval = stats.kendalltau(
            range(len(df)), df["avg_commits_per_push"].values
        )
        results["trend"] = {
            "kendall_tau": float(tau),
            "p_value": float(tau_pval),
            "direction": "increasing" if tau > 0 else "decreasing",
            "significant": tau_pval < 0.05,
        }

    # Dispersion analysis: is the spread (p75-p25) growing?
    if "p75_commits_per_push" in df.columns and "p25_commits_per_push" in df.columns:
        df["iqr"] = df["p75_commits_per_push"] - df["p25_commits_per_push"]
        iqr_pre = df_pre["p75_commits_per_push"].values - df_pre["p25_commits_per_push"].values
        iqr_post = df_post["p75_commits_per_push"].values - df_post["p25_commits_per_push"].values

        if len(iqr_pre) > 0 and len(iqr_post) > 0:
            results["dispersion"] = {
                "iqr_pre_mean": float(np.mean(iqr_pre)),
                "iqr_post_mean": float(np.mean(iqr_post)),
                "iqr_change_percent": float(
                    (np.mean(iqr_post) - np.mean(iqr_pre)) / max(np.mean(iqr_pre), 1e-10) * 100
                ),
                "interpretation": (
                    "Growing dispersion suggests bifurcation: some developers pushing "
                    "much larger batches (AI-assisted) while others maintain small pushes"
                ),
            }

    return results


def print_report(results: dict) -> None:
    """Print commit size analysis report."""
    print("=" * 60)
    print("COMMIT SIZE DISTRIBUTION REPORT")
    print("=" * 60)

    for metric, stats_dict in results.items():
        if metric in ("trend", "dispersion"):
            print(f"\n--- {metric.upper()} ---")
            for k, v in stats_dict.items():
                print(f"  {k}: {v}")
        elif isinstance(stats_dict, dict) and "pre_mean" in stats_dict:
            sig = "*" if stats_dict.get("significant") else " "
            print(f"\n{sig} {metric}:")
            print(f"    Pre-AI mean:    {stats_dict['pre_mean']:.3f}")
            print(f"    Post-AI mean:   {stats_dict['post_mean']:.3f}")
            print(f"    Change:         {stats_dict['percent_change_mean']:+.1f}%")
            print(f"    p-value:        {stats_dict['p_value']:.4f}")

    print("=" * 60)


if __name__ == "__main__":
    data_file = DATA_DIR / "commit_size_distribution.csv"

    if not data_file.exists():
        print("Generating synthetic commit size data for demonstration...")
        np.random.seed(42)

        rows = []
        for year in range(2020, 2026):
            for quarter in range(1, 5):
                if year == 2025 and quarter > 3:
                    break

                base_avg = 2.5
                base_median = 2.0

                # Gradual increase
                idx = (year - 2020) * 4 + quarter
                base_avg += idx * 0.02
                base_median += idx * 0.01

                # Post-ChatGPT bump
                if year > 2022 or (year == 2022 and quarter >= 4):
                    months_post = ((year - 2022) * 4 + quarter - 4) * 3
                    base_avg += 0.3 + months_post * 0.02
                    base_median += 0.2 + months_post * 0.01

                rows.append({
                    "year": year,
                    "quarter": quarter,
                    "total_push_events": int(50_000_000 + idx * 2_000_000 + np.random.randint(-500_000, 500_000)),
                    "avg_commits_per_push": base_avg + np.random.normal(0, 0.1),
                    "p25_commits_per_push": max(1, base_median - 0.5 + np.random.normal(0, 0.05)),
                    "median_commits_per_push": base_median + np.random.normal(0, 0.05),
                    "p75_commits_per_push": base_median + 1.5 + np.random.normal(0, 0.1),
                    "p95_commits_per_push": base_avg + 5 + np.random.normal(0, 0.3),
                    "stddev_commits_per_push": 3.0 + idx * 0.05 + np.random.normal(0, 0.1),
                })

        pd.DataFrame(rows).to_csv(data_file, index=False)
        print(f"Synthetic data written to {data_file}")

    results = analyse_distribution_shift(load_commit_size_data())
    print_report(results)
