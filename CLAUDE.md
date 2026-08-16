# GitHub Explosion — Project Guide

Live dashboard: [botcommits.dev](https://botcommits.dev)

## What this project does

Tracks AI-generated commits on public GitHub repos using BigQuery (GH Archive) and GitHub Search API. Measures growth of Claude Code, Aider, Devin, and OpenAI Codex CLI by detecting commit attribution markers (Co-Authored-By trailers, author emails, commit message patterns).

## Key numbers (as of Feb 2026)

- Claude Code: 24 commits (Jan 2025) → 5.19M/month (Feb 2026) = 216,000x growth
- AI share: ~7.85% of push events, ~19.6% estimated code volume (2.5x adjustment for larger diffs)
- Claude holds 96% of detectable AI commit market share
- Best fit: exponential (R²=0.989), doubling every ~1.38 months, no saturation observed
- Copilot and Cursor are invisible to this methodology (no commit-level markers)

## Project structure

```
dashboard/index.html       — Single-page Chart.js dashboard (deployed to Cloud Run)
analysis/claude_commits.py — BigQuery query runner (--query, --months flags) — Jan–Oct 2025 only
analysis/search_collector.py — GitHub Search API collector for Nov 2025+ (windowed, repeated draws, resumable)
analysis/fit_models.py     — Exponential/Logistic/Gompertz curve fitting (scipy)
analysis/changepoint.py    — Structural break detection (Pelt algorithm)
analysis/visualize.py      — Matplotlib publication-quality plots
analysis/nlp_pipeline.py   — Commit message feature analysis (pre vs post AI)
queries/claude_commits.sql — 6 parameterized BigQuery queries
data/                      — CSV exports (timeseries, all_tools, total_pushes, top_repos)
config.py                  — Constants, paths, BigQuery settings
run_pipeline.py            — Orchestrator for all analysis steps (1-5)
```

## Common commands

```bash
# Collect Nov 2025+ monthly counts via Search API (resumable; ~15-25 s per call)
.venv/bin/python -m analysis.search_collector --months 2025-11..2026-08
.venv/bin/python -m analysis.search_collector --list        # tool queries + calibration notes

# Run unit tests
.venv/bin/python -m pytest tests -q

# Fit growth models (generates JSON for dashboard)
python -m analysis.fit_models

# Query BigQuery for a specific month (requires gcloud auth)
python -m analysis.claude_commits --query all_tools --months 202501

# Dry run (shows query + cost estimate, no charge)
python -m analysis.claude_commits --dry-run --query all_tools --months 202501

# Run full pipeline
python run_pipeline.py

# Run single step
python run_pipeline.py --step 2

# Local dashboard
cd dashboard && python3 -m http.server 9443
```

## Data sources

- **Jan–Oct 2025:** GH Archive via BigQuery (~400 GB/month scans, exact counts)
- **Nov 2025+:** GitHub Search API via `analysis/search_collector.py`. GH Archive PushEvent payload is now only `{repository_id, push_id, ref, head, before}` (verified 2026-01-15 and 2026-07-15 samples) — no commits array, so BigQuery cannot detect tools or count devs after Oct 2025.
- **Search API caveats:** `total_count` is a timed-out estimate (`incomplete_results: true` on every heavy query). Biased low by 30-40 % for windows holding >~5 M results; ±15 % call-to-call noise, occasionally 2×. The collector splits months into <1.5 M-result windows, draws each 3×, sums medians, and logs every raw call to `data/search_api_raw.jsonl`.
- **Total push events:** BigQuery aggregation (cheap, no payload scan)

## Known issues

- Oct 2025 GH Archive data is incomplete (61M vs ~71M events) — excluded from model fitting
- GitHub Search API counts are approximate, not exact
- Private repos (81.5% of GitHub) are unmeasurable — dashboard shows speculative extrapolation
- Attribution bias: Claude auto-adds trailers (80.5% attribution rate) vs Copilot (9%)

## Costs

- First BigQuery load (14 months): ~$30
- Monthly update: ~$2–3
- Dashboard hosting: Cloud Run free tier
