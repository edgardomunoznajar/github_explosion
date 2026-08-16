"""
Assemble the dashboard data blob and render dashboard/index.html from
dashboard/index.template.html.

Inputs
    data/model_fits.json            (analysis.fit_models)
    data/search_api_monthly.csv     (analysis.search_collector)
    data/claude_total_pushes.csv    (BigQuery Query 5)
Output
    dashboard/index.html            (template with /*__DATA__*/ replaced)
    dashboard/data.json             (same blob, for anyone who wants the numbers)

Usage:  python -m analysis.build_dashboard
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from config import DATA_DIR, PROJECT_ROOT
from analysis.fit_models import BQ, BQ_MONTHS

DASH = PROJECT_ROOT / "dashboard"
TEMPLATE = DASH / "index.template.html"
OUT_HTML = DASH / "index.html"
OUT_JSON = DASH / "data.json"

TOOL_ORDER = ["claude", "copilot_agent", "copilot_coauthor", "jules", "openai_codex", "gemini_assist", "devin", "aider"]
TOOL_LABEL = {
    "claude": "Claude Code", "copilot_agent": "Copilot coding agent (bot-authored)",
    "copilot_coauthor": "Copilot coding agent (squash-merged, trailer)", "jules": "Jules (Google)",
    "openai_codex": "OpenAI Codex", "gemini_assist": "Gemini Code Assist", "devin": "Devin", "aider": "Aider",
}


def build_blob() -> dict:
    fits = json.loads((DATA_DIR / "model_fits.json").read_text())
    months: list[str] = fits["labels"]
    search = pd.read_csv(DATA_DIR / "search_api_monthly.csv")
    pushes = pd.read_csv(DATA_DIR / "claude_total_pushes.csv")
    pushes["month"] = pushes.apply(lambda r: f"{int(r.year):04d}-{int(r.month):02d}", axis=1)
    push_map = dict(zip(pushes.month, pushes.total_push_events.astype(int)))

    # per-tool monthly series over the full label range: BigQuery for Jan–Sep 2025, Search API after
    est = search.pivot(index="month", columns="tool", values="estimate")
    tools = {}
    for tool in TOOL_ORDER:
        row = []
        for m in months:
            if m in BQ_MONTHS and tool in BQ:
                row.append(int(BQ[tool][BQ_MONTHS.index(m)]))
            elif m in est.index and tool in est.columns and pd.notna(est.loc[m, tool]):
                row.append(int(est.loc[m, tool]))
            else:
                row.append(None)
        tools[tool] = row

    partial = fits["series"]["partial"]
    last_full_idx = max(i for i, p in enumerate(partial) if not p)
    last_full = months[last_full_idx]
    total6 = fits["series"]["total6"]

    def slim(fit: dict) -> dict:
        keys = ("params", "aic", "r2", "doubling_months", "ceiling", "inflection_t", "runaway", "fitted", "n")
        return {k: fit[k] for k in keys if k in fit}

    blob = {
        "updated": date.today().isoformat(),
        "labels": months,
        "proj_labels": fits["projection_labels"],
        "partial": partial,
        "source": fits["series"]["source"],
        "last_full_month": last_full,
        "last_full_idx": last_full_idx,
        "claude": fits["series"]["claude"],
        "claude_lo": fits["series"]["claude_lo"],
        "claude_hi": fits["series"]["claude_hi"],
        "total6": total6,
        "tools": tools,
        "tool_labels": TOOL_LABEL,
        "pushes": {m: push_map.get(m) for m in months},
        "fits": {col: {name: slim(f) for name, f in fits["fits"][col]["fits"].items() if "params" in f}
                 for col in ("claude", "total6")},
        "best": {col: fits["fits"][col]["best_by_aic"] for col in ("claude", "total6")},
        "hindcast": {col: {name: slim(f) for name, f in fits["hindcast"][col]["fits"].items() if "params" in f}
                     for col in ("claude", "total6")},
        "hindcast_through": fits["hindcast"]["claude"]["through"],
        "sensitivity": fits["sensitivity"],
    }
    # headline numbers
    i, p = last_full_idx, last_full_idx - 1
    c, c_prev = blob["claude"][i], blob["claude"][p]
    blob["headline"] = {
        "claude_last": c, "claude_mom_pct": round((c / c_prev - 1) * 100),
        "total6_last": total6[i], "total6_mom_pct": round((total6[i] / total6[p] - 1) * 100),
        "share_last_pct": round(total6[i] / push_map[last_full] * 100, 1) if push_map.get(last_full) else None,
        "doubling_now": round(fits["fits"]["claude"]["fits"]["exponential"]["doubling_months"], 2),
        "doubling_march": round(fits["hindcast"]["claude"]["fits"]["exponential"]["doubling_months"], 2),
        "march_exp_pred_last_full": fits["hindcast"]["claude"]["fits"]["exponential"]["fitted"][last_full_idx],
        "logistic_ceiling": round(fits["fits"]["claude"]["fits"]["logistic"]["ceiling"]),
        "gompertz_ceiling": round(fits["fits"]["claude"]["fits"]["gompertz"]["ceiling"]),
        "inflection_month": fits["projection_labels"][int(round(fits["fits"]["claude"]["fits"]["logistic"]["inflection_t"]))],
        "growth_since_jan25": round(c / 24),
        "cumulative_claude": int(sum(v for v in blob["claude"] if v)),
    }
    return blob


def render(blob: dict) -> str:
    tpl = TEMPLATE.read_text()
    assert "/*__DATA__*/" in tpl, "template placeholder missing"
    return tpl.replace("/*__DATA__*/", "const DATA = " + json.dumps(blob, separators=(",", ":")) + ";")


def main() -> None:
    blob = build_blob()
    OUT_JSON.write_text(json.dumps(blob, indent=1))
    OUT_HTML.write_text(render(blob))
    h = blob["headline"]
    print(f"Rendered {OUT_HTML} ({OUT_HTML.stat().st_size:,} bytes); last full month {blob['last_full_month']}: "
          f"Claude {h['claude_last']:,} ({h['claude_mom_pct']:+d}% MoM), share {h['share_last_pct']}%, "
          f"doubling now {h['doubling_now']} mo vs March fit {h['doubling_march']} mo, "
          f"logistic ceiling {h['logistic_ceiling']:,}")


if __name__ == "__main__":
    main()
