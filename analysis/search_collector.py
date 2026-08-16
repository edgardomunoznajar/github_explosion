"""
GitHub Search API collector for AI-attributed commits (Nov 2025 onward).

Why this exists
---------------
GH Archive dropped the ``commits[]`` array from PushEvent payloads in Oct 2025,
so the BigQuery detection queries in ``queries/claude_commits.sql`` return
nothing after that month. The only remaining public instrument is
``GET /search/commits``, whose ``total_count`` has two known defects that this
module is built around:

1. **Timeout truncation.** Every response carries ``incomplete_results: true``.
   Empirically the reported count is close to the truth for windows holding
   fewer than ~2–3 M commits, and 30–40 % *low* for windows holding 15–20 M
   (July 2026: whole-month calls 11.6 M / 14.3 M vs. 18.6 M summed over four
   weekly windows). We therefore never trust a single large window: months are
   split into windows sized so each holds < ``--cap`` results, and the window
   counts are summed.

2. **Call-to-call noise.** The same query over the same window drifts by
   ±15 % typically and up to 2× occasionally (Mar 2026: 8.19 M vs 5.70 M).
   Each window is therefore queried ``--draws`` times and the median is used;
   min/max sums are reported as a crude interval.

Every raw call is appended to ``data/search_api_raw.jsonl`` so a run can be
resumed for free and the noise can be studied later.

Usage
-----
    python -m analysis.search_collector --months 2026-03 2026-04 --tools claude
    python -m analysis.search_collector --months 2025-11..2026-08          # all tools
    python -m analysis.search_collector --plan --months 2026-07             # no calls
    python -m analysis.search_collector --list

Rate limits: /search is 30 req/min but secondary limits bite far earlier on
these heavy queries; the client sleeps ``--gap`` seconds between calls and
honours ``Retry-After``. Budget roughly 15–25 s per call.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from config import DATA_DIR

RAW_LOG = DATA_DIR / "search_api_raw.jsonl"
MONTHLY_CSV = DATA_DIR / "search_api_monthly.csv"
METHOD_TAG = "search_api_windowed_v1"

# One query per tool. Commit search has no trailer qualifier, so tools that
# leave a trailer use a phrase search (heavy: always incomplete_results=true,
# noisy); tools that commit from a bot account use `author:` (cheap, exact,
# incomplete_results=false). Calibrated 2026-08-16 against the Feb 2026 values
# hand-collected for the dashboard in March 2026 ("hand" below). Where the
# hand value cannot be reproduced the original query is unknown; the query
# chosen here is the one that mirrors the BigQuery detection signal in
# queries/claude_commits.sql. Treat those series as discontinuous at 2026-02.
TOOLS: dict[str, dict] = {
    "claude": {
        "q": '"Co-Authored-By: Claude"',
        "note": "trailer phrase. Feb26 hand 5,187,311; this query 4 draws 3.95–5.40M, median 5.18M.",
    },
    "jules": {
        "q": "author:google-labs-jules[bot]",
        "note": "bot author, exact. Feb26 hand 129,069; this query 121,725.",
    },
    "devin": {
        "q": "author:devin-ai-integration[bot]",
        "note": "bot author, exact. Feb26 hand 3,978 (unreproducible); this 13,551; trailer phrase 13,715.",
    },
    "aider": {
        "q": '"Co-authored-by: aider"',
        "note": "trailer phrase. Feb26 hand 6,422; this 6,132. ('aider:' prefix phrase gives 12,121.)",
    },
    "gemini_assist": {
        "q": '"Co-authored-by: gemini-code-assist"',
        "note": "trailer phrase. Feb26 hand 8,979 (unreproducible); this 18,088.",
    },
    "openai_codex": {
        "q": "noreply@openai.com",
        "note": "author/co-author e-mail (SQL signal). Feb26 hand 7,119 (unreproducible); this 74,003; 'Co-authored-by: Codex' 17,679.",
    },
    "copilot_agent": {
        "q": "author:copilot-swe-agent[bot]",
        "note": "Copilot coding agent bot author, exact. NEW (not in dashboard). Feb26 554,707 — 4x Jules; falls to ~113K by Jun26.",
    },
    "copilot_coauthor": {
        "q": '"Co-authored-by: Copilot"',
        "note": "Copilot trailer phrase (user-authored commits). NEW. Feb26 151,495. Collected to test whether the bot-author drop is an authorship change.",
    },
}

DEFAULT_CAP = 1_500_000      # max expected results per window before splitting
DEFAULT_DRAWS = 3            # repeated calls per window
DEFAULT_GAP = 10.0           # seconds between calls
INFLATE = 1.6                # whole-month probe is biased low; inflate before sizing windows
DATE_FIELD = "committer-date"


# ────────────────────────────────────────────────────────────────────────────
# HTTP client
# ────────────────────────────────────────────────────────────────────────────

def _token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as e:
        raise SystemExit("No GitHub token: set GITHUB_TOKEN or run `gh auth login`") from e


class SearchClient:
    """Minimal, polite /search/commits client. One method: count()."""

    def __init__(self, gap: float = DEFAULT_GAP, max_calls: int | None = None, log_path: Path = RAW_LOG):
        self.gap = gap
        self.max_calls = max_calls
        self.calls = 0
        self.log_path = log_path
        self._token = _token()
        self._last_call = 0.0

    def count(self, tool: str, q: str, start: date, end: date, draw: int) -> tuple[int, bool]:
        if self.max_calls is not None and self.calls >= self.max_calls:
            raise RuntimeError(f"--max-calls {self.max_calls} reached")
        full_q = f"{q} {DATE_FIELD}:{start.isoformat()}..{end.isoformat()}"
        url = "https://api.github.com/search/commits?per_page=1&q=" + urllib.parse.quote(full_q, safe="")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "botcommits-search-collector",
        }
        backoff = 60.0
        for attempt in range(8):
            wait = self.gap - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            t0 = time.monotonic()
            status = None
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as r:
                    status = r.status
                    body = json.load(r)
                    retry_after = None
            except urllib.error.HTTPError as e:
                status = e.code
                body = None
                retry_after = e.headers.get("Retry-After")
                reset = e.headers.get("X-RateLimit-Reset")
                if status in (403, 429):
                    if retry_after:
                        sleep_for = float(retry_after) + 1
                    elif reset:
                        sleep_for = max(5.0, float(reset) - time.time() + 1)
                    else:
                        sleep_for = backoff
                        backoff = min(backoff * 2, 600)
                elif status >= 500:
                    sleep_for = backoff
                    backoff = min(backoff * 2, 600)
                else:
                    raise
                print(f"    HTTP {status} — sleeping {sleep_for:.0f}s", file=sys.stderr)
                self._last_call = time.monotonic()
                time.sleep(sleep_for)
                continue
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                print(f"    network error {e!r} — sleeping {backoff:.0f}s", file=sys.stderr)
                time.sleep(backoff)
                backoff = min(backoff * 2, 600)
                continue
            finally:
                self._last_call = time.monotonic()
                self.calls += 1

            total = int(body["total_count"])
            incomplete = bool(body.get("incomplete_results", False))
            self._log({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "tool": tool, "q": q, "date_field": DATE_FIELD,
                "start": start.isoformat(), "end": end.isoformat(), "draw": draw,
                "total_count": total, "incomplete_results": incomplete,
                "http_status": status, "elapsed_s": round(time.monotonic() - t0, 2),
            })
            return total, incomplete
        raise RuntimeError(f"gave up after 8 attempts: {full_q}")

    def _log(self, rec: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(rec) + "\n")


# ────────────────────────────────────────────────────────────────────────────
# Cache of prior raw calls (resume for free)
# ────────────────────────────────────────────────────────────────────────────

def load_raw_cache(log_path: Path = RAW_LOG) -> dict[tuple, int]:
    """(tool, q, start, end, draw) -> total_count for every logged call."""
    cache: dict[tuple, int] = {}
    if not log_path.exists():
        return cache
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            cache[(r["tool"], r["q"], r["start"], r["end"], r["draw"])] = int(r["total_count"])
    return cache


# ────────────────────────────────────────────────────────────────────────────
# Window planning (pure functions — unit tested)
# ────────────────────────────────────────────────────────────────────────────

def month_bounds(month: str, today: date | None = None) -> tuple[date, date, bool]:
    """'YYYY-MM' -> (first_day, last_day, is_partial). Partial months end yesterday UTC."""
    y, m = (int(x) for x in month.split("-"))
    first = date(y, m, 1)
    last = date(y, m, calendar.monthrange(y, m)[1])
    today = today or datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    if last >= today:
        return first, min(last, yesterday), True
    return first, last, False


def split_range(start: date, end: date, n: int) -> list[tuple[date, date]]:
    """Split [start, end] (inclusive) into n contiguous, roughly equal day windows."""
    days = (end - start).days + 1
    n = max(1, min(n, days))
    out = []
    cursor = start
    for i in range(n):
        size = days // n + (1 if i < days % n else 0)
        w_end = cursor + timedelta(days=size - 1)
        out.append((cursor, w_end))
        cursor = w_end + timedelta(days=1)
    return out


def plan_windows(start: date, end: date, probe: int, cap: int, inflate: float = INFLATE) -> list[tuple[date, date]]:
    """Choose an initial window count from a (biased-low) whole-range probe."""
    import math
    n = max(1, math.ceil(probe * inflate / cap))
    return split_range(start, end, n)


def expand_months(tokens: list[str]) -> list[str]:
    """['2025-11..2026-02', '2026-04'] -> ['2025-11','2025-12','2026-01','2026-02','2026-04']"""
    out: list[str] = []
    for tok in tokens:
        if ".." in tok:
            a, b = tok.split("..")
            y, m = (int(x) for x in a.split("-"))
            y2, m2 = (int(x) for x in b.split("-"))
            while (y, m) <= (y2, m2):
                out.append(f"{y:04d}-{m:02d}")
                m += 1
                if m == 13:
                    y, m = y + 1, 1
        else:
            out.append(tok)
    return out


# ────────────────────────────────────────────────────────────────────────────
# Collection
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class WindowResult:
    start: date
    end: date
    draws: list[int] = field(default_factory=list)

    @property
    def median(self) -> int:
        return int(statistics.median(self.draws))


@dataclass
class MonthResult:
    tool: str
    month: str
    estimate: int
    lo: int
    hi: int
    n_windows: int
    n_draws: int
    probe_whole_month: int
    partial: bool
    days_covered: int
    method: str = METHOD_TAG


def _draw_window(client: SearchClient | None, cache: dict, tool: str, q: str,
                 start: date, end: date, draws: int) -> WindowResult:
    wr = WindowResult(start, end)
    for d in range(draws):
        key = (tool, q, start.isoformat(), end.isoformat(), d)
        if key in cache:
            wr.draws.append(cache[key])
            continue
        if client is None:
            raise RuntimeError("plan mode: no client")
        n, incomplete = client.count(tool, q, start, end, d)
        cache[key] = n
        wr.draws.append(n)
        if d == 0 and not incomplete:
            # exact result (bot-author queries): repeats are identical, don't spend them
            break
    return wr


def collect_month(tool: str, month: str, client: SearchClient | None, cache: dict,
                  cap: int = DEFAULT_CAP, draws: int = DEFAULT_DRAWS, verbose: bool = True) -> MonthResult:
    q = TOOLS[tool]["q"]
    start, end, partial = month_bounds(month)
    # 1. probe whole month once (draw index 0)
    probe = _draw_window(client, cache, tool, q, start, end, 1).draws[0]
    # 2. size windows from the probe, then draw each; split any window that still exceeds cap
    pending = plan_windows(start, end, probe, cap)
    windows: list[WindowResult] = []
    while pending:
        w_start, w_end = pending.pop(0)
        # first draw only: if it already exceeds cap, split before spending the other draws
        first = _draw_window(client, cache, tool, q, w_start, w_end, 1)
        if first.draws[0] > cap and w_start != w_end:
            pending = split_range(w_start, w_end, 2) + pending
            continue
        wr = _draw_window(client, cache, tool, q, w_start, w_end, draws)
        if wr.median > cap and w_start != w_end:
            pending = split_range(w_start, w_end, 2) + pending
            continue
        windows.append(wr)
    windows.sort(key=lambda w: w.start)
    est = sum(w.median for w in windows)
    lo = sum(min(w.draws) for w in windows)
    hi = sum(max(w.draws) for w in windows)
    if verbose:
        flag = " (partial)" if partial else ""
        print(f"  {tool:14s} {month}{flag}: probe {probe:>12,}  ->  {len(windows):>2} windows, "
              f"estimate {est:>12,}  [{lo:,} – {hi:,}]")
    return MonthResult(tool, month, est, lo, hi, len(windows), draws, probe, partial,
                       (end - start).days + 1)


def write_monthly(results: list[MonthResult], path: Path = MONTHLY_CSV) -> pd.DataFrame:
    """Merge new results into the monthly CSV (tool+month is the key; newer wins)."""
    new = pd.DataFrame([asdict(r) for r in results])
    if path.exists():
        old = pd.read_csv(path)
        merged = pd.concat([old, new], ignore_index=True)
        merged = merged.drop_duplicates(subset=["tool", "month"], keep="last")
    else:
        merged = new
    merged = merged.sort_values(["tool", "month"]).reset_index(drop=True)
    merged.to_csv(path, index=False)
    return merged


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Collect AI-attributed commit counts via GitHub Search API")
    p.add_argument("--months", nargs="+", help="e.g. 2026-03 2026-04 or 2025-11..2026-08")
    p.add_argument("--tools", nargs="+", default=list(TOOLS), choices=list(TOOLS))
    p.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    p.add_argument("--cap", type=int, default=DEFAULT_CAP)
    p.add_argument("--gap", type=float, default=DEFAULT_GAP)
    p.add_argument("--max-calls", type=int, default=None, help="safety stop")
    p.add_argument("--plan", action="store_true", help="use cached calls only; error if a call would be needed")
    p.add_argument("--list", action="store_true")
    args = p.parse_args(argv)

    if args.list:
        for name, spec in TOOLS.items():
            print(f"  {name:14s} {spec['q']:45s} {spec['note']}")
        return
    if not args.months:
        p.print_help()
        return

    months = expand_months(args.months)
    cache = load_raw_cache()
    client = None if args.plan else SearchClient(gap=args.gap, max_calls=args.max_calls)
    print(f"Collecting {len(args.tools)} tools × {len(months)} months  (cap={args.cap:,}, draws={args.draws}, "
          f"{len(cache)} cached calls)")
    n_rows = 0
    try:
        for month in months:
            month_results: list[MonthResult] = []
            for tool in args.tools:
                try:
                    month_results.append(collect_month(tool, month, client, cache, args.cap, args.draws))
                except RuntimeError as e:
                    print(f"  {tool:14s} {month}: stopped — {e}", file=sys.stderr)
                    if args.plan:
                        continue
                    raise
                finally:
                    # flush after every tool-month so a crash or kill loses nothing
                    if month_results:
                        write_monthly(month_results)
            n_rows += len(month_results)
    finally:
        print(f"\nWrote {n_rows} rows -> {MONTHLY_CSV}")
        if client:
            print(f"API calls this run: {client.calls}")


if __name__ == "__main__":
    main()
