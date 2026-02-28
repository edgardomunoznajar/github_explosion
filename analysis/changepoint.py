"""
Step 2: Changepoint detection in per-developer push velocity.

Applies the Pelt algorithm (Pruned Exact Linear Time) to detect
structural breaks in the time series. If the model finds a
breakpoint at Nov 2022 - Feb 2023, that's the AI adoption signal.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import ruptures as rpt
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    CHANGEPOINT_MODEL,
    CHANGEPOINT_PENALTY,
    CHATGPT_LAUNCH,
    COPILOT_GA,
    DATA_DIR,
    VIZ_DIR,
)


def load_push_velocity(filepath: Path | None = None) -> pd.DataFrame:
    """Load the per-developer push velocity CSV exported from BigQuery."""
    if filepath is None:
        filepath = DATA_DIR / "monthly_pushes_per_dev.csv"

    df = pd.read_csv(filepath)
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2) + "-01"
    )
    df = df.sort_values("date").reset_index(drop=True)
    return df


def detect_changepoints(
    signal: np.ndarray,
    model: str = CHANGEPOINT_MODEL,
    penalty: float = CHANGEPOINT_PENALTY,
) -> list[int]:
    """
    Detect changepoints using the Pelt algorithm.

    Returns list of breakpoint indices (0-indexed into the signal array).
    The last element is always len(signal) (end sentinel) — we strip it.
    """
    algo = rpt.Pelt(model=model, min_size=3, jump=1).fit(signal)
    breakpoints = algo.predict(pen=penalty)
    # Remove the end sentinel
    return [bp for bp in breakpoints if bp < len(signal)]


def run_segmented_regression(df: pd.DataFrame, breakpoint_idx: int) -> dict:
    """
    Fit a piecewise linear regression around the detected breakpoint.

    Returns slopes and R² for pre- and post-break segments.
    """
    x = np.arange(len(df))
    y = df["pushes_per_dev"].values

    # Pre-break segment
    x_pre, y_pre = x[:breakpoint_idx], y[:breakpoint_idx]
    slope_pre, intercept_pre, r_pre, p_pre, _ = stats.linregress(x_pre, y_pre)

    # Post-break segment
    x_post, y_post = x[breakpoint_idx:], y[breakpoint_idx:]
    slope_post, intercept_post, r_post, p_post, _ = stats.linregress(x_post, y_post)

    return {
        "pre_break": {
            "slope": slope_pre,
            "intercept": intercept_pre,
            "r_squared": r_pre**2,
            "p_value": p_pre,
            "n_months": len(x_pre),
        },
        "post_break": {
            "slope": slope_post,
            "intercept": intercept_post,
            "r_squared": r_post**2,
            "p_value": p_post,
            "n_months": len(x_post),
        },
        "slope_change_ratio": slope_post / slope_pre if slope_pre != 0 else float("inf"),
    }


def welch_t_test(df: pd.DataFrame, breakpoint_idx: int) -> dict:
    """
    Welch's t-test comparing mean pushes_per_dev before and after the breakpoint.
    """
    pre = df["pushes_per_dev"].values[:breakpoint_idx]
    post = df["pushes_per_dev"].values[breakpoint_idx:]
    t_stat, p_value = stats.ttest_ind(pre, post, equal_var=False)

    return {
        "pre_mean": float(np.mean(pre)),
        "post_mean": float(np.mean(post)),
        "percent_change": float((np.mean(post) - np.mean(pre)) / np.mean(pre) * 100),
        "t_statistic": float(t_stat),
        "p_value": float(p_value),
        "significant_at_005": p_value < 0.05,
    }


def analyse(filepath: Path | None = None) -> dict:
    """
    Run the full changepoint analysis.

    Returns a dict with breakpoints, regression results, and significance tests.
    """
    df = load_push_velocity(filepath)
    signal = df["pushes_per_dev"].values

    # Detect changepoints
    breakpoints = detect_changepoints(signal)

    # Map breakpoint indices back to dates
    breakpoint_dates = [df.iloc[bp]["date"].strftime("%Y-%m") for bp in breakpoints]

    results = {
        "n_months": len(df),
        "date_range": f"{df['date'].min().strftime('%Y-%m')} to {df['date'].max().strftime('%Y-%m')}",
        "breakpoints": {
            "indices": breakpoints,
            "dates": breakpoint_dates,
        },
        "chatgpt_launch": CHATGPT_LAUNCH,
        "copilot_ga": COPILOT_GA,
    }

    # For each breakpoint, run segmented regression and t-test
    for i, (bp_idx, bp_date) in enumerate(zip(breakpoints, breakpoint_dates)):
        key = f"breakpoint_{i}_{bp_date}"
        results[key] = {
            "regression": run_segmented_regression(df, bp_idx),
            "t_test": welch_t_test(df, bp_idx),
        }

    # Check if any breakpoint falls near ChatGPT launch (within 3 months)
    chatgpt_date = pd.Timestamp(CHATGPT_LAUNCH + "-01")
    near_chatgpt = [
        d for d in breakpoint_dates
        if abs((pd.Timestamp(d + "-01") - chatgpt_date).days) <= 90
    ]
    results["breakpoint_near_chatgpt"] = len(near_chatgpt) > 0
    results["nearest_to_chatgpt"] = near_chatgpt[0] if near_chatgpt else None

    return results


def print_report(results: dict) -> None:
    """Print a human-readable report of the changepoint analysis."""
    print("=" * 60)
    print("CHANGEPOINT ANALYSIS REPORT")
    print("=" * 60)
    print(f"Data range: {results['date_range']}")
    print(f"Months analysed: {results['n_months']}")
    print(f"ChatGPT launch: {results['chatgpt_launch']}")
    print(f"Copilot GA: {results['copilot_ga']}")
    print()
    print(f"Detected breakpoints: {results['breakpoints']['dates']}")
    print(f"Breakpoint near ChatGPT launch (±3 months): {results['breakpoint_near_chatgpt']}")

    if results["nearest_to_chatgpt"]:
        print(f"Nearest breakpoint to ChatGPT: {results['nearest_to_chatgpt']}")

    for key, val in results.items():
        if not key.startswith("breakpoint_") or key in ("breakpoint_near_chatgpt",):
            continue
        if not isinstance(val, dict):
            continue

        print(f"\n--- {key} ---")
        reg = val["regression"]
        print(f"  Pre-break slope:  {reg['pre_break']['slope']:.4f} pushes/dev/month")
        print(f"  Post-break slope: {reg['post_break']['slope']:.4f} pushes/dev/month")
        print(f"  Slope change:     {reg['slope_change_ratio']:.2f}x")
        print(f"  Pre R²: {reg['pre_break']['r_squared']:.3f}, Post R²: {reg['post_break']['r_squared']:.3f}")

        tt = val["t_test"]
        print(f"  Pre-break mean:   {tt['pre_mean']:.2f}")
        print(f"  Post-break mean:  {tt['post_mean']:.2f}")
        print(f"  Change:           {tt['percent_change']:+.1f}%")
        print(f"  Welch's t:        {tt['t_statistic']:.3f} (p={tt['p_value']:.4f})")
        print(f"  Significant:      {tt['significant_at_005']}")

    print("=" * 60)


if __name__ == "__main__":
    # Generate synthetic data for testing if no real data exists
    data_file = DATA_DIR / "monthly_pushes_per_dev.csv"
    if not data_file.exists():
        print("No data file found. Generating synthetic data for demonstration...")
        dates = pd.date_range("2020-01-01", "2025-08-01", freq="MS")
        np.random.seed(42)

        pushes_per_dev = []
        for i, d in enumerate(dates):
            base = 15.0
            # Gradual growth pre-ChatGPT
            base += i * 0.05
            # Step change post-ChatGPT (Nov 2022 = index ~34)
            if d >= pd.Timestamp("2022-11-01"):
                base += 3.0
                # Accelerating growth post-AI
                months_post = (d - pd.Timestamp("2022-11-01")).days / 30
                base += months_post * 0.15
            pushes_per_dev.append(base + np.random.normal(0, 0.8))

        df = pd.DataFrame({
            "year": dates.year,
            "month": dates.month,
            "total_pushes": [int(p * 5_000_000) for p in pushes_per_dev],
            "unique_pushers": [5_000_000 + i * 50_000 for i in range(len(dates))],
            "pushes_per_dev": pushes_per_dev,
        })
        df.to_csv(data_file, index=False)
        print(f"Synthetic data written to {data_file}")

    results = analyse()
    print_report(results)
