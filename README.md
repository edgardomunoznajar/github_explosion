# GitHub Explosion: Quantifying the Vibe Coding Era

**Research question:** Did per-developer commit velocity increase post-ChatGPT (Nov 2022), controlling for developer population growth? And can we detect AI-generated code signals in commit metadata?

## Background

GitHub crossed 1 billion commits in 2025 (+25.1% YoY), with 43.2M pull requests merged per month. Over 1.1M public repos now import an LLM SDK (+178% YoY). This project applies statistical and NLP methods to determine how much of this growth is attributable to AI-assisted "vibe coding."

## Data Sources

- **GH Archive** (`gharchive.org`): Every public GitHub event since 2011, queryable via Google BigQuery (`githubarchive.month.*`)
- **GitHub Innovation Graph** (`innovationgraph.github.com`): Pre-aggregated monthly counts by country and language

## Pipeline

| Phase | Description | Tool |
|-------|-------------|------|
| 1. Aggregation | Per-developer push velocity time series | BigQuery SQL |
| 2. Changepoint Detection | Structural break analysis around Nov 2022 | Python (ruptures) |
| 3. Commit Message NLP | Embedding drift + AI-written classifier | SentenceTransformers + GPU |
| 4. Commit Size Distribution | Shift in commits-per-push over time | BigQuery + Python |
| 5. Visualization | Time series, distributions, UMAP clusters | matplotlib/plotly |

## Project Structure

```
github_explosion/
├── queries/              # BigQuery SQL files
│   ├── push_velocity.sql
│   ├── commit_size_distribution.sql
│   └── commit_messages_sample.sql
├── analysis/             # Python analysis modules
│   ├── __init__.py
│   ├── changepoint.py    # Step 2: changepoint detection
│   ├── nlp_pipeline.py   # Step 3: commit message NLP
│   ├── commit_size.py    # Step 4: size distribution analysis
│   └── visualize.py      # Step 5: plots and figures
├── data/                 # Exported CSVs (gitignored)
├── notebooks/            # Jupyter notebooks for exploration
├── visualizations/       # Generated plots
├── config.py             # Configuration and constants
├── run_pipeline.py       # Main orchestrator
└── requirements.txt
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run BigQuery queries first (requires gcloud auth)
# Export results to data/ directory

# Run the full analysis pipeline
python run_pipeline.py

# Or run individual steps
python -m analysis.changepoint
python -m analysis.nlp_pipeline
python -m analysis.commit_size
python -m analysis.visualize
```

## Estimated Cost

| Phase | Time | Cost |
|-------|------|------|
| BigQuery aggregation | 1-2 days | $0 (free tier) |
| Changepoint analysis | 1 day | $0 |
| Commit message NLP | 3-5 days | ~$5-20 BigQuery egress |
| Write-up / visualisation | 2-3 days | $0 |

## Expected Findings

1. Structural break in per-developer push velocity: late 2022 to mid-2023
2. Commit message length and formality increasing post-2023
3. Python/TypeScript repos showing stronger AI signals than C/C++
4. Smaller repos (solo/hobby = vibe coders) showing stronger velocity increases than large org repos
