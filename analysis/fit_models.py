"""
Fit exponential / logistic / Gompertz growth models to monthly AI-attributed
commit counts and write the fitted curves + projections for the dashboard.

Series construction
-------------------
* Jan–Sep 2025: BigQuery exact counts (GH Archive PushEvent payloads).
* Oct 2025 onward: GitHub Search API via ``analysis.search_collector``
  (``data/search_api_monthly.csv``), which also fills the Oct 2025 month that
  BigQuery lost to the payload-format change.
* Excluded from fitting: 2025-01 (24 commits, pre-launch seed) and any partial
  month (current month).

Fitting
-------
Primary fits are ordinary least squares in linear space on Feb 2025 onward —
the same method the March-2026 dashboard used, so the hindcast reproduces its
claim. Linear space is dominated by the high-volume months, which is what the
"where is the ceiling" question needs. Because a 3-parameter sigmoid on ~18
points is sensitive to weighting and window, a sensitivity table is also
written (log-space weighted by the collector's lo/hi bands; Search-API-era-only
window) and the ceiling range across configurations is reported. Runaway fits
(ceiling at the 1e10 bound) are flagged, not used.

A hindcast is also produced: the same three models fitted only through
2026-03 (the last month on the March 2026 dashboard), so the page can show what
that fit predicted for Apr–Aug 2026 against what was observed.

Usage:  python -m analysis.fit_models   ->  data/model_fits.json  (+ console summary)
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from config import DATA_DIR

OUT_JSON = DATA_DIR / "model_fits.json"
SEARCH_CSV = DATA_DIR / "search_api_monthly.csv"

# BigQuery era (exact) — from data/claude_all_tools.csv, Jan–Sep 2025.
# Oct 2025 is dropped here on purpose: the payload change mid-month truncated it.
BQ_MONTHS = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06", "2025-07", "2025-08", "2025-09"]
BQ = {
    "claude":        [24, 2139, 23273, 21703, 43017, 224256, 440682, 557127, 486418],
    "jules":         [21, 25, 126, 188, 26297, 62720, 42590, 70848, 63173],
    "devin":         [2093, 2294, 3609, 3404, 6227, 3435, 4518, 5006, 2320],
    "aider":         [205, 399, 347, 289, 278, 986, 7894, 6737, 5130],
    "gemini_assist": [17, 10, 300, 257, 494, 2755, 8880, 14014, 12416],
    "openai_codex":  [374, 234, 254, 1474, 852, 558, 1037, 1669, 1465],
}
SIX_TOOLS = list(BQ)          # the tools the site has always summed as "total AI"
BQ_SIGMA_LOG = 0.05
SEARCH_SIGMA_FLOOR = 0.10
HINDCAST_LAST = "2026-03"     # last month on the March-2026 dashboard
PROJECT_MONTHS = 12


# ── series ──────────────────────────────────────────────────────────────────

def _next_months(last: str, n: int) -> list[str]:
    y, m = (int(x) for x in last.split("-"))
    out = []
    for _ in range(n):
        m += 1
        if m == 13:
            y, m = y + 1, 1
        out.append(f"{y:04d}-{m:02d}")
    return out


def build_series(search_csv: Path = SEARCH_CSV) -> pd.DataFrame:
    """One row per month: claude, total6, sigma_log_*, source, partial."""
    s = pd.read_csv(search_csv)
    s = s[s.tool.isin(SIX_TOOLS)]
    piv_est = s.pivot(index="month", columns="tool", values="estimate")
    piv_lo = s.pivot(index="month", columns="tool", values="lo")
    piv_hi = s.pivot(index="month", columns="tool", values="hi")
    partial = s.groupby("month")["partial"].any()

    rows = []
    for i, m in enumerate(BQ_MONTHS):
        rows.append({
            "month": m, "source": "bigquery", "partial": False,
            "claude": BQ["claude"][i], "total6": sum(BQ[t][i] for t in SIX_TOOLS),
            "claude_lo": BQ["claude"][i], "claude_hi": BQ["claude"][i],
            "sigma_claude": BQ_SIGMA_LOG, "sigma_total6": BQ_SIGMA_LOG,
        })
    for m in sorted(piv_est.index):
        if m <= BQ_MONTHS[-1]:
            continue  # BigQuery wins where both exist
        est, lo, hi = piv_est.loc[m], piv_lo.loc[m], piv_hi.loc[m]
        if est.isna().any():
            continue  # month not fully collected for all six tools
        c, c_lo, c_hi = float(est["claude"]), float(lo["claude"]), float(hi["claude"])
        tot, tot_lo, tot_hi = float(est.sum()), float(lo.sum()), float(hi.sum())
        rows.append({
            "month": m, "source": "search_api", "partial": bool(partial.loc[m]),
            "claude": int(c), "total6": int(tot),
            "claude_lo": int(c_lo), "claude_hi": int(c_hi),
            "sigma_claude": max(SEARCH_SIGMA_FLOOR, (c_hi - c_lo) / (2 * c)),
            "sigma_total6": max(SEARCH_SIGMA_FLOOR, (tot_hi - tot_lo) / (2 * tot)),
        })
    return pd.DataFrame(rows)


# ── models (in log space) ───────────────────────────────────────────────────

def exponential(t, a, b):
    return a * np.exp(b * t)


def logistic(t, L, k, t0):
    return L / (1.0 + np.exp(-k * (t - t0)))


def gompertz(t, L, k, t0):
    return L * np.exp(-np.exp(-k * (t - t0)))


MODELS = {
    "exponential": (exponential, lambda t, y: ([y[0], 0.5], ([1e-3, 0.0], [1e9, 5.0]))),
    "logistic":    (logistic,    lambda t, y: ([y.max() * 3, 0.5, t[-1]], ([y.max() * 0.5, 0.01, 0.0], [1e10, 5.0, 60.0]))),
    "gompertz":    (gompertz,    lambda t, y: ([y.max() * 3, 0.3, t[-1] - 2], ([y.max() * 0.5, 0.01, 0.0], [1e10, 5.0, 60.0]))),
}


def fit_one(name: str, t: np.ndarray, y: np.ndarray, sigma_log: np.ndarray, space: str = "lin") -> dict:
    """space='lin': OLS on y. space='log': WLS on log(y) with sigma_log weights."""
    f, init = MODELS[name]
    p0, bounds = init(t, y)
    if space == "log":
        def g(tt, *p):
            return np.log(np.clip(f(tt, *p), 1e-9, None))
        yy, sigma = np.log(y), sigma_log
    else:
        g, yy, sigma = f, y, None
    popt, _ = curve_fit(g, t, yy, p0=p0, sigma=sigma, absolute_sigma=False, bounds=bounds, maxfev=400000)
    resid = yy - g(t, *popt)
    if sigma is not None:
        resid = resid / sigma
    n, k = len(y), len(popt)
    rss = float(np.sum(resid ** 2))
    aic = n * math.log(rss / n) + 2 * k          # Gaussian AIC, residual scale estimated
    ss_tot = float(np.sum((yy - yy.mean()) ** 2)) if sigma is None else float(np.sum(((yy - yy.mean()) / sigma) ** 2))
    out = {"params": dict(zip(f.__code__.co_varnames[1:1 + k], map(float, popt))),
           "aic": aic, "r2": 1 - rss / ss_tot, "n": n, "space": space}
    if name == "exponential":
        out["doubling_months"] = math.log(2) / popt[1]
    else:
        out["ceiling"] = float(popt[0])
        out["inflection_t"] = float(popt[2])
        out["runaway"] = bool(popt[0] >= 1e9)
    return out


def predict(name: str, params: dict, t: np.ndarray) -> list[int]:
    f = MODELS[name][0]
    return [int(round(v)) for v in f(t, *params.values())]


def fit_series(df: pd.DataFrame, col: str, last_month: str | None = None,
               start_month: str = "2025-02", space: str = "lin") -> dict:
    """Fit all models on df[col] over [start_month, last_month], excluding partial months."""
    d = df.copy()
    d["t"] = np.arange(len(d))
    use = d[(d.month >= start_month) & (~d.partial)]
    if last_month:
        use = use[use.month <= last_month]
    t, y, sig = use.t.values.astype(float), use[col].values.astype(float), use[f"sigma_{col}"].values
    fits = {}
    for name in MODELS:
        try:
            fits[name] = fit_one(name, t, y, sig, space)
        except Exception as e:  # noqa: BLE001 — report and continue
            fits[name] = {"error": str(e)}
    ok = {k: v for k, v in fits.items() if "aic" in v and not v.get("runaway")}
    best = min(ok, key=lambda k: ok[k]["aic"]) if ok else None
    return {"fits": fits, "best_by_aic": best, "months_used": use.month.tolist(),
            "space": space, "start_month": start_month, "last_month": last_month}


# ── main ────────────────────────────────────────────────────────────────────

def main() -> dict:
    df = build_series()
    months = df.month.tolist()
    proj_labels = months + _next_months(months[-1], PROJECT_MONTHS)
    t_proj = np.arange(len(proj_labels), dtype=float)

    out = {
        "generated_from": {"search_csv": str(SEARCH_CSV.name), "bq_months": BQ_MONTHS},
        "labels": months,
        "projection_labels": proj_labels,
        "series": {
            "claude": df.claude.tolist(), "claude_lo": df.claude_lo.tolist(), "claude_hi": df.claude_hi.tolist(),
            "total6": df.total6.tolist(), "source": df.source.tolist(), "partial": df.partial.tolist(),
        },
        "fits": {}, "hindcast": {}, "sensitivity": {},
    }
    SENS = [("lin", "2025-02"), ("lin", "2025-06"), ("lin", "2025-11"), ("log", "2025-02"), ("log", "2025-06"), ("log", "2025-11")]
    for col in ("claude", "total6"):
        r = fit_series(df, col)
        for name, fit in r["fits"].items():
            if "params" in fit:
                fit["fitted"] = predict(name, fit["params"], t_proj)
        out["fits"][col] = r
        h = fit_series(df, col, last_month=HINDCAST_LAST)
        for name, fit in h["fits"].items():
            if "params" in fit:
                fit["fitted"] = predict(name, fit["params"], t_proj)
        out["hindcast"][col] = h | {"through": HINDCAST_LAST}
        rows = []
        for space, start in SENS:
            sr = fit_series(df, col, start_month=start, space=space)
            row = {"space": space, "start": start, "n": len(sr["months_used"]), "best": sr["best_by_aic"]}
            for name, fit in sr["fits"].items():
                if "aic" not in fit:
                    continue
                row[f"{name}_aic"] = round(fit["aic"], 1)
                if name == "exponential":
                    row["exp_doubling"] = round(fit["doubling_months"], 2)
                else:
                    row[f"{name}_ceiling"] = None if fit["runaway"] else round(fit["ceiling"])
                    row[f"{name}_t0"] = round(fit["inflection_t"], 1)
            rows.append(row)
        ceilings = [v for r_ in rows for k, v in r_.items() if k.endswith("_ceiling") and v]
        out["sensitivity"][col] = {
            "rows": rows,
            "sigmoid_wins": sum(1 for r_ in rows if r_["best"] in ("logistic", "gompertz")),
            "configs": len(rows),
            "ceiling_min": min(ceilings) if ceilings else None,
            "ceiling_max": max(ceilings) if ceilings else None,
        }

    OUT_JSON.write_text(json.dumps(out, indent=1))

    # console summary
    print(f"Series: {months[0]}..{months[-1]}  ({len(months)} months, "
          f"{sum(df.source == 'bigquery')} BigQuery + {sum(df.source == 'search_api')} Search API"
          f"{', last partial' if df.partial.iloc[-1] else ''})")
    for col in ("claude", "total6"):
        for label, block in (("FULL", out["fits"][col]), (f"HINDCAST≤{HINDCAST_LAST}", out["hindcast"][col])):
            print(f"\n[{col}] {label}  best={block['best_by_aic']}")
            for name, fit in block["fits"].items():
                if "aic" not in fit:
                    print(f"  {name:12s} FAILED {fit['error']}")
                    continue
                extra = (f"doubling {fit['doubling_months']:.2f} mo" if name == "exponential"
                         else f"ceiling {fit['ceiling']:,.0f}  inflection t={fit['inflection_t']:.1f} "
                              f"({proj_labels[int(round(fit['inflection_t']))] if fit['inflection_t'] < len(proj_labels) else 'beyond'})")
                last_obs = max(i for i, pm in enumerate(df.partial) if not pm)
                print(f"  {name:12s} AIC={fit['aic']:7.1f}  R²={fit['r2']:.3f}  {extra}"
                      f"  | {months[last_obs]}: fit {fit['fitted'][last_obs]:,} vs obs {df[col].iloc[last_obs]:,}"
                      f"  | +6mo {proj_labels[-1]}: {fit['fitted'][-1]:,}")
        sens = out["sensitivity"][col]
        print(f"\n[{col}] SENSITIVITY: sigmoid beats exponential in {sens['sigmoid_wins']}/{sens['configs']} configs; "
              f"ceiling range {sens['ceiling_min']:,} – {sens['ceiling_max']:,}")
        for r_ in sens["rows"]:
            print("   " + json.dumps(r_))
    print(f"\nWrote {OUT_JSON}")
    return out


if __name__ == "__main__":
    main()
