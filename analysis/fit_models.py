"""
Fit exponential, logistic, and Gompertz growth models to Claude commit data.
Compare AIC/BIC, output parameters for the dashboard.
"""

import json

import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import pearsonr

# Real data: Claude commits per month
# Index 9 (Oct 2025) is incomplete — exclude from fitting
labels = [
    "2025-01", "2025-02", "2025-03", "2025-04", "2025-05",
    "2025-06", "2025-07", "2025-08", "2025-09", "2025-10",
    "2025-11", "2025-12", "2026-01", "2026-02",
]
claude = [
    24, 2139, 23273, 21703, 43017,
    224256, 440682, 557127, 486418, 170227,
    1167145, 1553216, 3145469, 5187311,
]

# Exclude Oct 2025 (index 9) — incomplete data
mask = [i != 9 for i in range(len(claude))]
t_all = np.arange(len(claude))
t = t_all[mask]
y = np.array(claude)[mask]


# --- Model definitions ---

def exponential(t, a, b):
    """y = a * exp(b * t)"""
    return a * np.exp(b * t)


def logistic(t, L, k, t0):
    """y = L / (1 + exp(-k * (t - t0)))"""
    return L / (1.0 + np.exp(-k * (t - t0)))


def gompertz(t, L, k, t0):
    """y = L * exp(-exp(-k * (t - t0)))"""
    return L * np.exp(-np.exp(-k * (t - t0)))


# --- Fit each model ---

results = {}

# Exponential
try:
    popt, pcov = curve_fit(exponential, t, y, p0=[100, 0.5], maxfev=10000)
    y_pred = exponential(t, *popt)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot
    n, k_params = len(y), 2
    aic = n * np.log(ss_res / n) + 2 * k_params
    bic = n * np.log(ss_res / n) + k_params * np.log(n)
    results["exponential"] = {
        "params": {"a": popt[0], "b": popt[1]},
        "r2": r2, "aic": aic, "bic": bic,
    }
    print(f"Exponential:  a={popt[0]:.2f}, b={popt[1]:.4f}  R²={r2:.4f}  AIC={aic:.1f}")
except Exception as e:
    print(f"Exponential fit failed: {e}")

# Logistic
try:
    popt, pcov = curve_fit(
        logistic, t, y,
        p0=[10_000_000, 0.5, 10],
        maxfev=50000,
        bounds=([1e5, 0.01, 0], [1e9, 5, 30]),
    )
    y_pred = logistic(t, *popt)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot
    n, k_params = len(y), 3
    aic = n * np.log(ss_res / n) + 2 * k_params
    bic = n * np.log(ss_res / n) + k_params * np.log(n)
    results["logistic"] = {
        "params": {"L": popt[0], "k": popt[1], "t0": popt[2]},
        "r2": r2, "aic": aic, "bic": bic,
    }
    inflection_month = labels[int(round(popt[2]))] if int(round(popt[2])) < len(labels) else f"t={popt[2]:.1f}"
    print(f"Logistic:     L={popt[0]:,.0f}, k={popt[1]:.4f}, t0={popt[2]:.2f} ({inflection_month})")
    print(f"              R²={r2:.4f}  AIC={aic:.1f}")
    print(f"              Projected ceiling: {popt[0]:,.0f} commits/month")
except Exception as e:
    print(f"Logistic fit failed: {e}")

# Gompertz
try:
    popt, pcov = curve_fit(
        gompertz, t, y,
        p0=[10_000_000, 0.3, 8],
        maxfev=50000,
        bounds=([1e5, 0.01, 0], [1e9, 5, 30]),
    )
    y_pred = gompertz(t, *popt)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot
    n, k_params = len(y), 3
    aic = n * np.log(ss_res / n) + 2 * k_params
    bic = n * np.log(ss_res / n) + k_params * np.log(n)
    results["gompertz"] = {
        "params": {"L": popt[0], "k": popt[1], "t0": popt[2]},
        "r2": r2, "aic": aic, "bic": bic,
    }
    print(f"Gompertz:     L={popt[0]:,.0f}, k={popt[1]:.4f}, t0={popt[2]:.2f}")
    print(f"              R²={r2:.4f}  AIC={aic:.1f}")
    print(f"              Projected ceiling: {popt[0]:,.0f} commits/month")
except Exception as e:
    print(f"Gompertz fit failed: {e}")


# --- Generate fitted curves for dashboard (including 6-month projection) ---
print("\n--- Model comparison ---")
best = min(results.items(), key=lambda x: x[1]["aic"])
print(f"Best model by AIC: {best[0]}")

# Project 6 months ahead (to Sep 2026)
t_proj = np.arange(len(claude) + 6)
proj_labels = labels + ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]

print("\n--- Dashboard values (JSON) ---")
dashboard = {}
for name, res in results.items():
    p = res["params"]
    if name == "exponential":
        fitted = exponential(t_proj, p["a"], p["b"]).tolist()
    elif name == "logistic":
        fitted = logistic(t_proj, p["L"], p["k"], p["t0"]).tolist()
    elif name == "gompertz":
        fitted = gompertz(t_proj, p["L"], p["k"], p["t0"]).tolist()
    dashboard[name] = {
        "fitted": [round(v) for v in fitted],
        "r2": round(res["r2"], 4),
        "aic": round(res["aic"], 1),
        "params": {k: round(v, 4) if abs(v) < 1e6 else round(v) for k, v in p.items()},
    }

dashboard["projection_labels"] = proj_labels
print(json.dumps(dashboard, indent=2))
