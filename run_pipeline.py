#!/usr/bin/env python3
"""
GitHub Explosion: Main analysis pipeline orchestrator.

Runs all analysis steps sequentially and generates a summary report.

Usage:
    python run_pipeline.py                # Run all steps
    python run_pipeline.py --step 2       # Run only step 2 (changepoint)
    python run_pipeline.py --synthetic    # Generate synthetic data first
"""

import argparse
import json
import sys
from pathlib import Path

from config import DATA_DIR, VIZ_DIR


def step1_check_data():
    """Step 1: Verify BigQuery data exports exist."""
    print("\n" + "=" * 60)
    print("STEP 1: DATA VERIFICATION")
    print("=" * 60)

    required_files = {
        "monthly_pushes_per_dev.csv": "Push velocity time series",
        "commit_size_distribution.csv": "Commit size distribution",
        "commit_messages_pre_ai.csv": "Pre-AI commit messages sample",
        "commit_messages_post_ai.csv": "Post-AI commit messages sample",
    }

    all_present = True
    for filename, description in required_files.items():
        filepath = DATA_DIR / filename
        if filepath.exists():
            size_mb = filepath.stat().st_size / 1_048_576
            print(f"  [OK] {filename} ({size_mb:.1f} MB) — {description}")
        else:
            print(f"  [MISSING] {filename} — {description}")
            all_present = False

    if not all_present:
        print("\n  Some data files are missing.")
        print("  Run with --synthetic to generate demo data, or export from BigQuery.")
        print("  SQL queries are in queries/ directory.")

    return all_present


def step2_changepoint():
    """Step 2: Changepoint detection analysis."""
    print("\n" + "=" * 60)
    print("STEP 2: CHANGEPOINT DETECTION")
    print("=" * 60)

    from analysis.changepoint import analyse, print_report
    results = analyse()
    print_report(results)
    return results


def step3_nlp(use_embeddings: bool = False, device: str = "cuda"):
    """Step 3: Commit message NLP analysis."""
    print("\n" + "=" * 60)
    print("STEP 3: COMMIT MESSAGE NLP")
    print("=" * 60)

    from analysis.nlp_pipeline import (
        analyse_text_features,
        analyse_embeddings,
        print_report,
    )

    # Always run text features (fast, no GPU)
    text_results = analyse_text_features()
    print_report(text_results, mode="text_features")

    embedding_results = None
    if use_embeddings:
        embedding_results = analyse_embeddings(device=device)
        print_report(embedding_results, mode="embeddings")

    return {"text_features": text_results, "embeddings": embedding_results}


def step4_commit_size():
    """Step 4: Commit size distribution analysis."""
    print("\n" + "=" * 60)
    print("STEP 4: COMMIT SIZE DISTRIBUTION")
    print("=" * 60)

    from analysis.commit_size import load_commit_size_data, analyse_distribution_shift, print_report
    df = load_commit_size_data()
    results = analyse_distribution_shift(df)
    print_report(results)
    return results


def step5_visualize():
    """Step 5: Generate all plots."""
    print("\n" + "=" * 60)
    print("STEP 5: VISUALIZATION")
    print("=" * 60)

    from analysis.visualize import generate_all_plots
    generate_all_plots()


def generate_synthetic_data():
    """Generate synthetic demonstration data for all pipeline steps."""
    print("Generating synthetic data...")

    # Each module generates its own synthetic data when run directly
    print("  Generating push velocity data...")
    from analysis.changepoint import load_push_velocity
    try:
        load_push_velocity()
    except FileNotFoundError:
        pass
    # Run the module's __main__ to trigger synthetic generation
    import runpy
    runpy.run_module("analysis.changepoint", run_name="__main__")

    print("  Generating commit size data...")
    runpy.run_module("analysis.commit_size", run_name="__main__")

    print("  Generating commit message data...")
    runpy.run_module("analysis.nlp_pipeline", run_name="__main__")

    print("Synthetic data generation complete.")


def main():
    parser = argparse.ArgumentParser(
        description="GitHub Explosion: Quantifying the Vibe Coding Era"
    )
    parser.add_argument(
        "--step", type=int, choices=[1, 2, 3, 4, 5],
        help="Run a specific step only",
    )
    parser.add_argument(
        "--synthetic", action="store_true",
        help="Generate synthetic demo data before running",
    )
    parser.add_argument(
        "--embeddings", action="store_true",
        help="Run GPU-accelerated embedding analysis in step 3",
    )
    parser.add_argument(
        "--device", default="cuda", choices=["cuda", "cpu"],
        help="Device for embedding computation",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Save JSON results to this file",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("GITHUB EXPLOSION ANALYSIS PIPELINE")
    print("Quantifying the Vibe Coding Era")
    print("=" * 60)

    if args.synthetic:
        generate_synthetic_data()

    all_results = {}

    steps = {
        1: ("Data verification", step1_check_data),
        2: ("Changepoint detection", step2_changepoint),
        3: ("NLP analysis", lambda: step3_nlp(args.embeddings, args.device)),
        4: ("Commit size distribution", step4_commit_size),
        5: ("Visualization", step5_visualize),
    }

    steps_to_run = [args.step] if args.step else list(steps.keys())

    for step_num in steps_to_run:
        name, func = steps[step_num]
        try:
            result = func()
            all_results[f"step{step_num}_{name}"] = result
        except FileNotFoundError as e:
            print(f"\n  [ERROR] Step {step_num} failed: {e}")
            print("  Run with --synthetic to generate demo data first.")
        except Exception as e:
            print(f"\n  [ERROR] Step {step_num} failed: {e}")
            raise

    # Save results
    if args.output:
        output_path = Path(args.output)
        # Convert numpy types for JSON serialisation
        def convert(obj):
            if hasattr(obj, "item"):
                return obj.item()
            if hasattr(obj, "tolist"):
                return obj.tolist()
            return str(obj)

        with open(output_path, "w") as f:
            json.dump(all_results, f, indent=2, default=convert)
        print(f"\nResults saved to {output_path}")

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
