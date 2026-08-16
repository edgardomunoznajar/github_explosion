"""Unit tests for analysis.search_collector — no network."""

import json
from datetime import date

import pytest

from analysis import search_collector as sc


# ── month_bounds ────────────────────────────────────────────────────────────

def test_month_bounds_complete_month():
    assert sc.month_bounds("2026-02", today=date(2026, 8, 16)) == (date(2026, 2, 1), date(2026, 2, 28), False)


def test_month_bounds_partial_month_ends_yesterday():
    assert sc.month_bounds("2026-08", today=date(2026, 8, 16)) == (date(2026, 8, 1), date(2026, 8, 15), True)


def test_month_bounds_leap_year():
    assert sc.month_bounds("2028-02", today=date(2028, 6, 1))[1] == date(2028, 2, 29)


# ── split_range ─────────────────────────────────────────────────────────────

def test_split_range_contiguous_and_covering():
    start, end = date(2026, 7, 1), date(2026, 7, 31)
    wins = sc.split_range(start, end, 4)
    assert wins[0][0] == start and wins[-1][1] == end
    for (a_s, a_e), (b_s, b_e) in zip(wins, wins[1:]):
        assert (b_s - a_e).days == 1
    assert sum((e - s).days + 1 for s, e in wins) == 31
    # sizes differ by at most one day
    sizes = [(e - s).days + 1 for s, e in wins]
    assert max(sizes) - min(sizes) <= 1


def test_split_range_never_exceeds_day_count():
    wins = sc.split_range(date(2026, 8, 1), date(2026, 8, 3), 10)
    assert len(wins) == 3
    assert all(s == e for s, e in wins)


# ── plan_windows ────────────────────────────────────────────────────────────

def test_plan_windows_small_probe_single_window():
    wins = sc.plan_windows(date(2026, 2, 1), date(2026, 2, 28), probe=100_000, cap=1_500_000)
    assert wins == [(date(2026, 2, 1), date(2026, 2, 28))]


def test_plan_windows_large_probe_splits_with_inflation():
    # 11.6M probe * 1.6 / 1.5M -> 13 windows
    wins = sc.plan_windows(date(2026, 7, 1), date(2026, 7, 31), probe=11_600_000, cap=1_500_000)
    assert len(wins) == 13


# ── expand_months ───────────────────────────────────────────────────────────

def test_expand_months_range_and_singletons():
    assert sc.expand_months(["2025-11..2026-02", "2026-04"]) == [
        "2025-11", "2025-12", "2026-01", "2026-02", "2026-04"]


# ── collect_month with a fake client ───────────────────────────────────────

class FakeClient:
    """Deterministic stand-in: returns per-day rate * days, plus a draw offset; truncates big windows."""

    def __init__(self, per_day: int, cap_truncate: int | None = None):
        self.per_day = per_day
        self.cap_truncate = cap_truncate
        self.calls = 0
        self.seen = []

    def count(self, tool, q, start, end, draw):
        self.calls += 1
        self.seen.append((start, end, draw))
        days = (end - start).days + 1
        n = self.per_day * days + draw * 10  # draws differ so median/min/max are distinct
        if self.cap_truncate and n > self.cap_truncate:
            n = int(n * 0.65)  # mimic timeout truncation on large windows
        return n, True


def test_collect_month_small_tool_single_window(monkeypatch):
    monkeypatch.setattr(sc, "month_bounds", lambda m, today=None: (date(2026, 2, 1), date(2026, 2, 28), False))
    fake = FakeClient(per_day=100)  # 2,800/month
    cache = {}
    r = sc.collect_month("devin", "2026-02", fake, cache, cap=1_500_000, draws=3, verbose=False)
    assert r.n_windows == 1
    assert r.estimate == 2_800 + 10          # median of draws 0,1,2 -> draw 1
    assert r.lo == 2_800 and r.hi == 2_820
    # probe (draw 0, whole month) is reused as draw 0 of the single window: 1 probe + 2 more draws
    assert fake.calls == 3


def test_collect_month_large_tool_splits_and_sums(monkeypatch):
    monkeypatch.setattr(sc, "month_bounds", lambda m, today=None: (date(2026, 7, 1), date(2026, 7, 31), False))
    per_day = 600_000                       # 18.6M/month, like Claude in Jul 2026
    fake = FakeClient(per_day=per_day, cap_truncate=3_000_000)
    cache = {}
    r = sc.collect_month("claude", "2026-07", fake, cache, cap=1_500_000, draws=3, verbose=False)
    # final windows must each hold < cap  (<= 2 days at 600k/day)  -> at least 16 of them
    assert r.n_windows >= 16
    # oversize windows are abandoned after ONE draw, never given all three
    over = [(s, e) for s, e, _ in fake.seen if (e - s).days + 1 > 2]
    from collections import Counter
    assert all(n == 1 for n in Counter(over).values())
    # sum of medians recovers the true monthly total (draw offset 10 per window is the only error)
    assert abs(r.estimate - per_day * 31) <= 10 * r.n_windows
    assert r.probe_whole_month < r.estimate  # probe was truncated, estimate is not


def test_collect_month_uses_cache_without_client(monkeypatch):
    monkeypatch.setattr(sc, "month_bounds", lambda m, today=None: (date(2026, 2, 1), date(2026, 2, 28), False))
    q = sc.TOOLS["aider"]["q"]
    cache = {("aider", q, "2026-02-01", "2026-02-28", d): 6_400 + d for d in range(3)}
    r = sc.collect_month("aider", "2026-02", client=None, cache=cache, cap=1_500_000, draws=3, verbose=False)
    assert r.estimate == 6_401


def test_collect_month_plan_mode_raises_when_call_needed(monkeypatch):
    monkeypatch.setattr(sc, "month_bounds", lambda m, today=None: (date(2026, 2, 1), date(2026, 2, 28), False))
    with pytest.raises(RuntimeError):
        sc.collect_month("aider", "2026-02", client=None, cache={}, cap=1_500_000, draws=3, verbose=False)


# ── raw log round-trip ──────────────────────────────────────────────────────

def test_load_raw_cache_round_trip(tmp_path):
    log = tmp_path / "raw.jsonl"
    rec = {"tool": "claude", "q": '"Co-Authored-By: Claude"', "start": "2026-02-01", "end": "2026-02-14",
           "draw": 1, "total_count": 2227638, "incomplete_results": True}
    log.write_text(json.dumps(rec) + "\n\n")
    cache = sc.load_raw_cache(log)
    assert cache[("claude", '"Co-Authored-By: Claude"', "2026-02-01", "2026-02-14", 1)] == 2227638


# ── monthly CSV merge ───────────────────────────────────────────────────────

def test_write_monthly_upserts_on_tool_month(tmp_path):
    path = tmp_path / "monthly.csv"
    mk = lambda est: sc.MonthResult("claude", "2026-02", est, est, est, 1, 3, est, False, 28)
    sc.write_monthly([mk(100)], path)
    df = sc.write_monthly([mk(200), sc.MonthResult("jules", "2026-02", 5, 5, 5, 1, 3, 5, False, 28)], path)
    assert len(df) == 2
    assert int(df[df.tool == "claude"].estimate.iloc[0]) == 200
