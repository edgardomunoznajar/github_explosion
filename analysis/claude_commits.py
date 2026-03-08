"""
Query and analyse Claude-attributed commits from GH Archive via BigQuery.

Queries are parameterised by month (MONTH_PLACEHOLDER) because each month
of PushEvents is ~200 GB. The free tier is 1 TB/month, so we iterate
month-by-month and concatenate results.

Usage:
    python -m analysis.claude_commits --query sample --months 2025_01
    python -m analysis.claude_commits --query timeseries --months 2024_06 2024_07 2024_08
    python -m analysis.claude_commits --query total_pushes   # no month iteration needed
    python -m analysis.claude_commits --dry-run --months 2025_01
    python -m analysis.claude_commits --list
"""

import argparse

import pandas as pd
from google.cloud import bigquery

from config import DATA_DIR, QUERIES_DIR

CLIENT = None

QUERY_SECTIONS = {
    "timeseries": "Query 1: Claude commits per month",
    "top_repos": "Query 2: Top repos by Claude commits",
    "model_breakdown": "Query 3: Attribution by model variant",
    "sample": "Query 4: Sample commits with metadata",
    "all_tools": "Query 6: All AI tools in one scan (Claude, Aider, Devin, Codex)",
    "total_pushes": "Query 5: Total push count (no payload scan, cheap)",
}

# Queries that need month-by-month iteration
MONTHLY_QUERIES = {"timeseries", "top_repos", "model_breakdown", "sample", "all_tools"}


def get_client():
    global CLIENT
    if CLIENT is None:
        CLIENT = bigquery.Client()
    return CLIENT


def _load_sql() -> str:
    return (QUERIES_DIR / "claude_commits.sql").read_text()


def _extract_query(sql_text: str, section_marker: str) -> str:
    """Extract a single query from the SQL file by its section comment."""
    sections = sql_text.split("-- ============================================================")
    for i, section in enumerate(sections):
        if section_marker in section:
            query_parts = []
            j = i + 1
            while j < len(sections):
                part = sections[j].strip()
                if part.startswith("--") and "Query" in part:
                    break
                if part and not part.startswith("-- ="):
                    query_parts.append(part)
                    break
                j += 1
            return "\n".join(query_parts).strip().rstrip(";")
    raise ValueError(f"Section '{section_marker}' not found in SQL file")


def parse_queries(sql_text: str) -> dict[str, str]:
    """Parse the SQL file into individual named queries."""
    queries = {}
    markers = {
        "timeseries": "Query 1:",
        "top_repos": "Query 2:",
        "model_breakdown": "Query 3:",
        "sample": "Query 4:",
        "all_tools": "Query 6:",
        "total_pushes": "Query 5:",
    }
    for name, marker in markers.items():
        try:
            queries[name] = _extract_query(sql_text, marker)
        except ValueError:
            print(f"  Warning: could not parse query '{name}'")
    return queries


def run_query_for_month(
    name: str, query_template: str, month: str, dry_run: bool = False
) -> pd.DataFrame:
    """Run a query for a single month, replacing MONTH_PLACEHOLDER."""
    client = get_client()
    sql = query_template.replace("MONTH_PLACEHOLDER", month)

    if dry_run:
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        job = client.query(sql, job_config=job_config)
        gb = job.total_bytes_processed / (1024 ** 3)
        cost = gb * (6.25 / 1024)  # $6.25/TB
        print(f"  [{name} | {month}] Estimated scan: {gb:.1f} GB (~${cost:.3f})")
        return pd.DataFrame()

    print(f"  Running {name} for {month}...")
    df = client.query(sql).to_dataframe()
    print(f"  [{name} | {month}] {len(df)} rows returned")
    return df


def run_query_global(name: str, query_sql: str, dry_run: bool = False) -> pd.DataFrame:
    """Run a query that doesn't need month parameterisation."""
    client = get_client()

    if dry_run:
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        job = client.query(query_sql, job_config=job_config)
        gb = job.total_bytes_processed / (1024 ** 3)
        cost = gb * (6.25 / 1024)
        print(f"  [{name}] Estimated scan: {gb:.1f} GB (~${cost:.3f})")
        return pd.DataFrame()

    print(f"  Running {name}...")
    df = client.query(query_sql).to_dataframe()
    print(f"  [{name}] {len(df)} rows returned")
    return df


def run(
    query_name: str,
    months: list[str] | None = None,
    dry_run: bool = False,
) -> pd.DataFrame:
    """Run a single named query across the specified months."""
    sql_text = _load_sql()
    queries = parse_queries(sql_text)

    if query_name not in queries:
        raise ValueError(f"Unknown query '{query_name}'. Available: {list(queries.keys())}")

    sql = queries[query_name]

    if query_name not in MONTHLY_QUERIES:
        df = run_query_global(query_name, sql, dry_run=dry_run)
        if not dry_run and not df.empty:
            out_path = DATA_DIR / f"claude_{query_name}.csv"
            df.to_csv(out_path, index=False)
            print(f"  Saved: {out_path}")
        return df

    if not months:
        print(f"  Error: --months required for '{query_name}' (e.g. --months 2025_01)")
        return pd.DataFrame()

    frames = []
    for m in months:
        df = run_query_for_month(query_name, sql, m, dry_run=dry_run)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    if not dry_run:
        out_path = DATA_DIR / f"claude_{query_name}.csv"
        combined.to_csv(out_path, index=False)
        print(f"  Saved: {out_path}")

    return combined


def main():
    parser = argparse.ArgumentParser(description="Query Claude commits from GH Archive")
    parser.add_argument(
        "--query", type=str, choices=list(QUERY_SECTIONS.keys()),
        help="Which query to run",
    )
    parser.add_argument(
        "--months", nargs="+", type=str,
        help="Month(s) to query, e.g. 202501 202502",
    )
    parser.add_argument("--list", action="store_true", help="List available queries")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Estimate cost without running queries",
    )
    args = parser.parse_args()

    if args.list:
        print("Available queries:")
        for name, desc in QUERY_SECTIONS.items():
            monthly = " (needs --months)" if name in MONTHLY_QUERIES else ""
            print(f"  {name:20s} — {desc}{monthly}")
        return

    if not args.query:
        parser.print_help()
        return

    run(args.query, months=args.months, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
