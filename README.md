# botcommits.dev — Tracking AI-Generated Commits on GitHub

Live dashboard: **[botcommits.dev](https://botcommits.dev)**

Claude Code went from 24 publicly-attributed commits in January 2025 to over 5.2 million per month in February 2026 — a 216,000x increase in 13 months. This project tracks that growth across four AI coding tools using real commit-level data.

## Key Findings

| Metric | Value |
|--------|-------|
| Claude commits, Jan 2025 | 24 |
| Claude commits, Feb 2026 | 5,187,311 |
| Growth multiple | 216,000x in 13 months |
| Claude market share | 96% of detectable AI commits |
| Total AI commits tracked | ~13M (cumulative) |
| Best fit growth model | Exponential (R²=0.989, AIC=314.7) |
| Logistic ceiling found? | No — converged to upper bound (~1B) |
| Peak repos with AI commits | 54,291 (Aug 2025) |
| Peak developers using AI | 36,692 (Aug 2025) |

## Tools Tracked

- **Claude Code** — Co-Authored-By trailers, commit body markers, author email (`noreply@anthropic.com`)
- **Aider** — `aider:` prefix in commit messages, Co-Authored-By trailers
- **Devin** — `devin-ai-integration` actor (BigQuery), `co-authored-by devin-ai` (Search API)
- **OpenAI Codex CLI** — Co-Authored-By trailers, author email (`noreply@openai.com`)

GitHub Copilot and Cursor do not leave commit-level attribution markers and are invisible to this methodology. The numbers here are a lower bound.

## Data Sources

- **Jan–Oct 2025**: [GH Archive](https://www.gharchive.org/) via Google BigQuery — exact commit-level counts from PushEvent payloads (~400 GB/month scans)
- **Nov 2025–present**: GitHub Search API — GH Archive stopped including commit message payloads in Nov 2025, reducing tables from ~400 GB to ~89 GB
- **Total push events**: BigQuery aggregation (no payload scan, cheap)

## Project Structure

```
github_explosion/
├── dashboard/
│   ├── index.html            # Live dashboard (Chart.js, single-page static)
│   ├── Dockerfile            # nginx:alpine container for Cloud Run
│   └── favicon.png           # Custom bot icon
├── analysis/
│   ├── claude_commits.py     # BigQuery query runner (--query, --months flags)
│   └── fit_models.py         # Exponential / Logistic / Gompertz curve fitting (scipy)
├── queries/
│   └── claude_commits.sql    # 6 BigQuery queries (timeseries, top repos, model breakdown, all tools, etc.)
├── data/
│   ├── claude_all_tools.csv  # AI commits by tool (Jan–Oct 2025, 4 tools × 10 months)
│   ├── claude_total_pushes.csv # Total push events per month (2024–2026)
│   ├── claude_timeseries.csv # Claude-only monthly timeseries
│   ├── claude_top_repos.csv  # Top repositories by Claude commit count
│   └── claude_sample.csv     # Sample commits with full metadata
├── requirements.txt
└── README.md
```

## Growth Model Fitting

Three models fitted to Claude commit counts using `scipy.optimize.curve_fit`:

| Model | R² | AIC | Parameters |
|-------|----|-----|------------|
| **Exponential** y = ae^(bt) | 0.989 | 314.7 | a=7506, b=0.502 |
| Logistic y = L/(1+e^(-k(t-t₀))) | 0.989 | 316.7 | L=1B (hit upper bound), k=0.504, t₀=23.5 |
| Gompertz y = Le^(-e^(-k(t-t₀))) | 0.981 | 323.8 | L=641M, k=0.093, t₀=30.0 |

The exponential model wins by AIC. The logistic model's ceiling parameter converged to its upper bound, meaning the data shows no evidence of saturation yet. This does **not** predict indefinite exponential growth — it means the inflection point of the S-curve has not yet been observed with 14 months of data.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run a BigQuery query (requires gcloud auth + project with BigQuery access)
python -m analysis.claude_commits --query all_tools --months 202501

# Dry run (shows query + estimated bytes, no charge)
python -m analysis.claude_commits --dry-run --query all_tools --months 202501

# Fit growth models to existing data
python -m analysis.fit_models

# Run the dashboard locally
cd dashboard && python3 -m http.server 9443
```

## Cost

- **First load** (14 months, all tools): ~$30 in BigQuery scan costs
- **Monthly update** (1 month, all tools): ~$2–3 per month
- **Total push counts**: ~$0.10 per query (no payload scan)
- **Dashboard hosting**: Cloud Run free tier

## Known Limitations

- **Oct 2025**: GH Archive data appears incomplete (61M push events vs ~71M adjacent months). Excluded from model fitting and growth rate calculations.
- **Nov 2025+**: GitHub Search API returns approximate `total_count` values, not exact counts.
- **Private repos**: Only public repos are measurable. 81.5% of GitHub activity is in private repos (GitHub Octoverse 2025). The dashboard shows a speculative upper bound extrapolation.
- **Attribution bias**: Claude Code automatically adds Co-Authored-By trailers. A paper (arXiv:2512.00867) found 80.5% of Claude-assisted commits include attribution vs 9% for Copilot. This methodology inherently favors tools with automatic attribution.

## Contributing

Contributions welcome — open an issue or submit a PR. Areas where help is especially useful:

- Additional AI tool detection signals
- Historical backfill to 2024
- Copilot detection via behavioral fingerprinting
- International/regional breakdowns
- Academic analysis and peer review

## License

Open source. Data, queries, and code are free to use for research, journalism, and analysis. Attribution appreciated.
