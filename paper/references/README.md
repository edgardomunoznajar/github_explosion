# References for the botcommits.dev paper

Downloaded 2026-08-16. PDFs are the arXiv version current on that date; `references.bib` holds the arXiv-generated BibTeX (keys as listed below).

| File | Key | What it is | Why we cite it |
|---|---|---|---|
| `arxiv-2605.25438.pdf` | `quispe2026agenticdelegationlanguagefrontier` | Quispe (Caltech). 7,786,771 Claude co-authored commits, Jan 2025–Jan 2026, 185,517 distinct authors; DiD on developer outcomes. | Independent replication of our cumulative Claude count (ours: 7,834,696, +0.6%). Adoption cohorts by quarter (1.6K/11.9K/46.7K/73.2K/52.2K) — first QoQ decline in new adopters in Q1 2026. |
| `arxiv-2606.24429.pdf` | `khosravani2026detectingaicodingagents` | Khosravani & Mockus. World of Code census, 180M repos, 3 snapshots Dec 2024–Apr 2026; 4-channel detection with validated precision. | Single-channel detection undercounts Claude Code 30×; "silent agents" (Copilot config in 92K projects, <0.5% commit attribution); Copilot coding agent had 1.13M attributed commits by Oct 2025 — a series we should add. |
| `arxiv-2601.18341.pdf` | `robbes2026agenticmuchadoptioncoding` | Robbes, Matricon, Degueule, Hora, Zacchiroli. 128K projects; 22–29% show agent traces as of Feb 2026. | Agent commits are larger than human-only commits — the citable source for our diff-size adjustment (currently uncited). Adoption spans project maturity. |
| `arxiv-2601.17406.pdf` | `ghaleb2026fingerprintingaicodingagents` | Ghaleb. XGBoost fingerprinting of Codex/Copilot/Cursor/Devin/Claude Code from PR/commit features, 97.2% F1 on 33,580 PRs. | The path to detecting marker-less tools (Copilot autocomplete, Cursor) that our method calls invisible. |
| `arxiv-2608.00966.pdf` | `ghaleb2026agentagattributionaicoding` | AgenTag — follow-up behavioral attribution. | Same as above, newer. |
| `arxiv-2512.00867.pdf` | `kraishan2025aiattributionparadoxtransparency` | Kraishan. 14,300 commits, 7,393 repos; disclosure rates 80.5% Claude vs 9.0% Copilot. | Marker-based counting is dominated by disclosure rate; cross-tool ratios on our site are mostly disclosure-rate ratios. |
| `arxiv-2603.28592.pdf` | `liu2026debtaiboomlargescale` | Debt Behind the AI Boom — large-scale study of AI-authored commits with explicit Git metadata traces. | Quality/tech-debt angle; also uses the same trace taxonomy we do. |
| `arxiv-2602.09185.pdf` | `li2026aidevstudyingaicoding` | AIDev dataset — AI-agent PRs on GitHub. | Dataset other fingerprinting papers build on; PR-level complement to our commit-level series. |
| `arxiv-2601.17581.pdf` | `ogenrwot2026aicodingagentsmodify` | How AI coding agents modify code — large-scale PR study. | Notes `Co-authored-by` casing variants; PR-level change characteristics. |
| `arxiv-2606.06843.pdf` | `mujahid2026empiricalstudycharacteristicsevolution` | AI-usage evidence from code comments in GitHub repos. | Alternative signal (comments, not trailers) for AI presence. |
| `octoverse-2025-github-blog.html` | — | GitHub Octoverse 2025 blog post. | Denominator context: ~986M commits in 2025 (+25% YoY), ~90–100M pushes/month; Copilot coding agent 1M+ PRs May–Sep 2025; 81.5% of contributions private. |

## Gaps to fill before writing

- No paper in this list publishes a **monthly public time series with a stated instrument**; that remains our contribution.
- Need a citable source for GH Archive's PushEvent payload change (Oct 2025: `commits[]` removed; ~Jun 2026: further shrink). Currently evidenced only by our BigQuery dry-run byte counts and a Jan/Jul 2026 payload sample (payload = `{repository_id, push_id, ref, head, before}` only).
- Need GitHub's own documentation of `incomplete_results` / timeout semantics for `/search/commits` `total_count`.
