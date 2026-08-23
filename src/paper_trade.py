"""
MEXC paper trade runner — MINA/USDT, KAVA/USDT, SFP/USDT, and XYO/USDT.

Run once per hour (cron or manual). On first run, initialises state but
places no trades. On subsequent runs, processes all completed 1h kline bars
since the last run and records fills, complete round-trips, and forced closes.

Fill detection mirrors the backtest exactly:
  bar's LOW  ≤ bid_limit  →  bid fill at bid_limit
  bar's HIGH ≥ ask_limit  →  ask fill at ask_limit
Queue position is not modelled — the same OHLCV-touch assumption used in
the backtest. This is intentional: we are tracking what the strategy would
have done, not simulating real execution.

Strategy params (same as backtest primary):
  spread      = 1.0%  (0.5% each side from mid)
  max_hold    = 3 bars  (3 hours; then force-close at 0.05% taker)
  MEXC fees   = 0% maker, 0.05% taker

State:   data/paper_trade_state.json   (persistent; overwrites on each run)
Events:  data/paper_trade_events.csv   (append-only; every fill and RT outcome)

Usage:
    python src/paper_trade.py                    # normal run
    python src/paper_trade.py --dry-run          # preview; no writes
    python src/paper_trade.py --status           # print state, no API calls
    python src/paper_trade.py --suspend MINAUSDT # mark pair suspended
    python src/paper_trade.py --resume  MINAUSDT # clear suspension
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PAIRS = ["MINAUSDT", "KAVAUSDT", "SFPUSDT", "XYOUSDT", "GOATUSDT", "XPRUSDT", "PIPPINUSDT", "SUSDT", "NILUSDT"]
BASE_URL = "https://api.mexc.com/api/v3/klines"
DATA_DIR = Path(__file__).parent.parent / "data"
STATE_FILE = DATA_DIR / "paper_trade_state.json"
EVENTS_FILE = DATA_DIR / "paper_trade_events.csv"

SPREAD_PCT = 1.0          # total spread; half posted each side
MAX_HOLD_BARS = 3         # hours before forced close
NOTIONAL_USDT = 50.0      # per fill (for dollar P&L tracking)
MAKER_FEE = 0.0000        # MEXC: 0% maker on limit orders that add liquidity
TAKER_FEE = 0.0005        # MEXC: 0.05% taker on forced close exit leg

# ── Spread-width cohort (forward-test, see docs/SPREAD_WIDTH_COHORT_2026-08-22.md) ──
# 7 live pairs x 6 widths (0.5-0.9% + a FRESH 1.0% control), all starting the
# same day so width is the only variable. Every instance gets a distinct key
# ("SYMBOL-WIDTH", e.g. "MINAUSDT-0.5") in state["pairs"] — this is what keeps
# them fully separate from the 7 original entries in PAIRS above (unchanged,
# untouched, still keyed by bare symbol e.g. "MINAUSDT" with original
# start_date_utc and 1.0% spread). Same NOTIONAL_USDT/MAX_HOLD_BARS/fees as
# every other instrument — only spread_pct varies per cohort group.
COHORT_BASE_PAIRS = ["MINAUSDT", "SFPUSDT", "XYOUSDT", "GOATUSDT", "XPRUSDT", "PIPPINUSDT", "SUSDT"]
COHORT_WIDTHS = [0.5, 0.6, 0.7, 0.8, 0.9]
COHORT_FRESH_CONTROL_WIDTH = 1.0   # fresh 1.0% control, own start date — isolates spread-width
                                    # effects from time-period effects (the gap in the prior
                                    # single-window backtest sweep)


def cohort_instance_id(symbol: str, width: float) -> str:
    suffix = f"{width:.1f}-FRESH" if width == COHORT_FRESH_CONTROL_WIDTH else f"{width:.1f}"
    return f"{symbol}-{suffix}"


def _build_cohort_instruments() -> dict:
    """instance_id -> {'symbol': MEXC symbol, 'spread_pct': float, 'width_label': str}"""
    out = {}
    for symbol in COHORT_BASE_PAIRS:
        for width in COHORT_WIDTHS + [COHORT_FRESH_CONTROL_WIDTH]:
            iid = cohort_instance_id(symbol, width)
            label = "1.0% (fresh control)" if width == COHORT_FRESH_CONTROL_WIDTH else f"{width:.1f}%"
            out[iid] = {"symbol": symbol, "spread_pct": width, "width_label": label}
    return out


COHORT_INSTRUMENTS = _build_cohort_instruments()   # 42 entries: 7 pairs x 6 widths
COHORT_WIDTH_GROUPS = COHORT_WIDTHS + [COHORT_FRESH_CONTROL_WIDTH]  # ordering for grouped display
COHORT_NOTES = {
    "PIPPINUSDT": ("Known risk: forced-close severity worsens at narrower "
                    "spreads (backtest finding, see docs/SPREAD_WIDTH_COHORT_2026-08-22.md)"),
}

# ── Hold/spread-width matrix cohort (forward-test, see docs/HOLD_SPREAD_MATRIX_2026-08-23.md) ──
# 7 live pairs x 5 max-hold windows (1h/2h/3h/4h/6h) x 2 spread widths
# (1.0%, 0.9%) = 70 instances, each with its own independent clock starting
# today. Distinct keys ("SYMBOL-WIDTH-Nh", e.g. "MINAUSDT-1.0-3h") that never
# collide with either the bare-symbol live-pair keys ("MINAUSDT") or the
# spread-width cohort's keys ("MINAUSDT-0.9", "MINAUSDT-1.0-FRESH") above —
# the "-Nh" suffix is what makes this cohort's keys distinct even where width
# values overlap (0.9 and 1.0 are both reused here). Same NOTIONAL_USDT/fees
# as every other instrument — only spread_pct and max_hold_bars vary per
# instance in this cohort.
HOLD_SPREAD_BASE_PAIRS = COHORT_BASE_PAIRS   # same 7 pairs
HOLD_SPREAD_WIDTHS = [1.0, 0.9]
HOLD_SPREAD_HOLDS = [1, 2, 3, 4, 6]          # hours == bars (1h klines)


def hold_spread_instance_id(symbol: str, width: float, hold_bars: int) -> str:
    return f"{symbol}-{width:.1f}-{hold_bars}h"


def _build_hold_spread_instruments() -> dict:
    """instance_id -> {'symbol', 'spread_pct', 'max_hold_bars', 'width_label', 'hold_label'}"""
    out = {}
    for symbol in HOLD_SPREAD_BASE_PAIRS:
        for width in HOLD_SPREAD_WIDTHS:
            for hold in HOLD_SPREAD_HOLDS:
                iid = hold_spread_instance_id(symbol, width, hold)
                out[iid] = {
                    "symbol": symbol,
                    "spread_pct": width,
                    "max_hold_bars": hold,
                    "width_label": f"{width:.1f}%",
                    "hold_label": f"{hold}h",
                }
    return out


HOLD_SPREAD_INSTRUMENTS = _build_hold_spread_instruments()   # 70 entries: 7 pairs x 2 widths x 5 holds

# ── NILUSDT-only spread-width cohort (forward-test, see
#    docs/NILUSDT_SPREAD_WIDTH_COHORT_2026-08-23.md) ──
# NIL was not part of the original 7-pair spread-width cohort above (it
# joined live paper trade later — see docs/HANDOFF_NILUSDT.md, added
# 2026-08-23 — after that cohort was already running). This is NIL's own,
# clearly separate 6-instance forward test: same widths (0.5-0.9% + a fresh
# 1.0% control), same instance-key convention (cohort_instance_id, reused
# as-is — "NILUSDT-0.5" ... "NILUSDT-1.0-FRESH"), same mechanics, but its
# own dict/keys/run function so the 7-pair cohort's code and data are never
# touched by this addition.
NIL_SPREAD_COHORT_SYMBOL = "NILUSDT"
NIL_SPREAD_COHORT_INSTRUMENTS = {
    cohort_instance_id(NIL_SPREAD_COHORT_SYMBOL, width): {
        "symbol": NIL_SPREAD_COHORT_SYMBOL,
        "spread_pct": width,
        "width_label": ("1.0% (fresh control)" if width == COHORT_FRESH_CONTROL_WIDTH
                         else f"{width:.1f}%"),
    }
    for width in COHORT_WIDTHS + [COHORT_FRESH_CONTROL_WIDTH]
}

# ── NILUSDT-only hold/spread-width matrix cohort (forward-test, see
#    docs/NILUSDT_HOLD_SPREAD_MATRIX_2026-08-23.md) ──
# Same rationale as above: NIL was not part of the 70-instance 7-pair
# hold/spread matrix. NIL's own 10-instance version (5 holds x 2 widths),
# same instance-key convention (hold_spread_instance_id, reused as-is —
# "NILUSDT-1.0-3h" etc.), own dict/keys/run function, isolated from the
# 70-instance matrix's code and data.
NIL_HOLD_SPREAD_INSTRUMENTS = {
    hold_spread_instance_id(NIL_SPREAD_COHORT_SYMBOL, width, hold): {
        "symbol": NIL_SPREAD_COHORT_SYMBOL,
        "spread_pct": width,
        "max_hold_bars": hold,
        "width_label": f"{width:.1f}%",
        "hold_label": f"{hold}h",
    }
    for width in HOLD_SPREAD_WIDTHS
    for hold in HOLD_SPREAD_HOLDS
}

EVENTS_HEADER = [
    "event_id", "run_utc", "pair", "event_type",
    "bar_open_ms", "bar_open_utc",
    "side", "fill_price", "mid_at_fill",
    "exit_price", "net_pct", "hold_bars", "notes",
]


# ── Time helpers ─────────────────────────────────────────────────────────────

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ms_to_utc(ms: int) -> str:
    return (datetime.fromtimestamp(ms / 1000, timezone.utc)
            .isoformat(timespec="seconds").replace("+00:00", "Z"))


# ── State management ─────────────────────────────────────────────────────────

def _blank_pair_state() -> dict:
    return {
        "start_date_utc": None,   # set on this pair's own first run (independent 30-day clock)
        "last_processed_bar_open_ms": None,
        "last_processed_bar_close": None,
        "suspended": False,
        "pending_bid": None,
        "pending_ask": None,
        "totals": {
            "fills": 0,
            "complete_rts": 0,
            "forced_closes": 0,
            "realized_pnl_pct_sum": 0.0,
        },
    }


def _blank_state() -> dict:
    return {
        "params": {
            "spread_pct": SPREAD_PCT,
            "max_hold_bars": MAX_HOLD_BARS,
            "notional_usdt": NOTIONAL_USDT,
            "maker_fee_pct": MAKER_FEE * 100,
            "taker_fee_pct": TAKER_FEE * 100,
        },
        "meta": {
            "start_date_utc": None,
            "last_run_utc": None,
        },
        "pairs": {pair: _blank_pair_state() for pair in PAIRS}
                 | {iid: _blank_pair_state() for iid in COHORT_INSTRUMENTS}
                 | {iid: _blank_pair_state() for iid in HOLD_SPREAD_INSTRUMENTS}
                 | {iid: _blank_pair_state() for iid in NIL_SPREAD_COHORT_INSTRUMENTS}
                 | {iid: _blank_pair_state() for iid in NIL_HOLD_SPREAD_INSTRUMENTS},
    }


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            state = json.load(f)
        # Migrate: add blank state for any pair newly added to PAIRS, and
        # backfill start_date_utc for pairs saved before it was tracked
        # per-pair (they inherit the old global meta start, preserving
        # their original decision date).
        pairs = state.setdefault("pairs", {})
        for pair in PAIRS:
            if pair not in pairs:
                pairs[pair] = _blank_pair_state()
            elif "start_date_utc" not in pairs[pair]:
                pairs[pair]["start_date_utc"] = state.get("meta", {}).get("start_date_utc")
        # Additive only: create blank state for any cohort instance not yet
        # seen. Never reads or writes an existing PAIRS entry above — cohort
        # instance keys (e.g. "MINAUSDT-0.5") are always distinct from the
        # bare-symbol keys (e.g. "MINAUSDT") used by the original 7 pairs.
        for instance_id in COHORT_INSTRUMENTS:
            if instance_id not in pairs:
                pairs[instance_id] = _blank_pair_state()
        # Additive only, same guarantee as above: create blank state for any
        # hold/spread-width matrix instance not yet seen. Never reads or
        # writes a PAIRS entry or a spread-width-cohort entry — matrix keys
        # (e.g. "MINAUSDT-1.0-3h") are always distinct from both.
        for instance_id in HOLD_SPREAD_INSTRUMENTS:
            if instance_id not in pairs:
                pairs[instance_id] = _blank_pair_state()
        # Additive only, same guarantee as above: create blank state for any
        # NIL-only spread-width cohort instance not yet seen. Never reads or
        # writes any other entry — NIL cohort keys (e.g. "NILUSDT-0.5") share
        # the same naming convention as the 7-pair cohort's keys but only
        # exist here because NIL is not among COHORT_BASE_PAIRS, so there is
        # no collision.
        for instance_id in NIL_SPREAD_COHORT_INSTRUMENTS:
            if instance_id not in pairs:
                pairs[instance_id] = _blank_pair_state()
        # Additive only, same guarantee: NIL-only hold/spread-width matrix.
        for instance_id in NIL_HOLD_SPREAD_INSTRUMENTS:
            if instance_id not in pairs:
                pairs[instance_id] = _blank_pair_state()
        return state
    return _blank_state()


def save_state(state: dict, dry_run: bool = False) -> None:
    if dry_run:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


# ── MEXC klines fetch ─────────────────────────────────────────────────────────

def fetch_klines(pair: str, since_ms: int | None = None, limit: int = 60) -> list[list]:
    """Return up to `limit` most-recent 1h klines. Last entry is the in-progress bar.
    If since_ms is provided, requests from that timestamp (up to 500 bars ≈ 20 days)."""
    if since_ms is not None:
        url = f"{BASE_URL}?symbol={pair}&interval=60m&startTime={since_ms}&limit=500"
    else:
        url = f"{BASE_URL}?symbol={pair}&interval=60m&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-mm-papertrade/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"  [fetch] ERROR for {pair}: {exc}", file=sys.stderr)
        return []
    if not isinstance(data, list) or not data:
        print(f"  [fetch] unexpected response for {pair}: {data}", file=sys.stderr)
        return []
    return data


def raw_to_bar(k: list) -> dict:
    """Convert MEXC kline array to named dict."""
    # MEXC format: [open_time_ms, open, high, low, close, vol_base, close_time_ms, vol_quote]
    return {
        "open_time_ms": int(k[0]),
        "open":  float(k[1]),
        "high":  float(k[2]),
        "low":   float(k[3]),
        "close": float(k[4]),
        "vol_quote": float(k[7]),
    }


# ── Events CSV ────────────────────────────────────────────────────────────────

def _ensure_events_header() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not EVENTS_FILE.exists():
        with open(EVENTS_FILE, "w", newline="") as f:
            csv.writer(f).writerow(EVENTS_HEADER)


def _event_row(e: dict) -> list:
    return [
        e.get("event_id", ""),
        e.get("run_utc", ""),
        e.get("pair", ""),
        e.get("event_type", ""),
        e.get("bar_open_ms", ""),
        e.get("bar_open_utc", ""),
        e.get("side", ""),
        e.get("fill_price", ""),
        e.get("mid_at_fill", ""),
        e.get("exit_price", ""),
        e.get("net_pct", ""),
        e.get("hold_bars", ""),
        e.get("notes", ""),
    ]


def append_events(events: list[dict], dry_run: bool = False) -> None:
    if not events:
        return
    if dry_run:
        for e in events:
            price = e.get("fill_price") or e.get("exit_price") or "?"
            print(f"  [dry-run] {e['event_type']:20s} {e['pair']}  price={price}  "
                  f"net={e.get('net_pct', '')}%")
        return
    _ensure_events_header()
    with open(EVENTS_FILE, "a", newline="") as f:
        w = csv.writer(f)
        for e in events:
            w.writerow(_event_row(e))


# ── Core: process bars for one pair ─────────────────────────────────────────

def _make_eid(pair: str, event_type: str, bar_open_ms: int) -> str:
    return f"{pair}-{event_type}-{bar_open_ms}"


def process_pair_bars(pair: str, ps: dict, bars: list[dict], run_utc: str,
                       spread_pct: float = SPREAD_PCT,
                       max_hold_bars: int = MAX_HOLD_BARS) -> list[dict]:
    """
    Process a chronological sequence of new completed bars for one pair.

    Each bar must have a 'prev_close' key set by the caller.
    Modifies ps (pair state) in-place.
    Returns list of event dicts to be appended to the events CSV.

    spread_pct defaults to the global SPREAD_PCT (1.0%) and max_hold_bars
    defaults to the global MAX_HOLD_BARS (3) — the original 7 pairs' call
    site below does not pass either, so their behavior is unchanged. The
    spread-width cohort passes its own width explicitly (default hold).
    The hold/spread-width matrix cohort passes both explicitly.
    """
    events: list[dict] = []
    spread_half = spread_pct / 200.0   # fraction, half-spread

    for bar in bars:
        open_ms = bar["open_time_ms"]
        open_utc = ms_to_utc(open_ms)
        mid = bar["prev_close"]

        bid_limit = mid * (1.0 - spread_half)
        ask_limit = mid * (1.0 + spread_half)

        # ── 1. Forced closes (checked before new fills, same as backtest) ──
        for side in ("bid", "ask"):
            pend = ps[f"pending_{side}"]
            if pend is None:
                continue
            bars_held = round((open_ms - pend["bar_open_ms"]) / 3_600_000)
            if bars_held < max_hold_bars:
                continue

            exit_px = bar["close"]
            if side == "bid":
                gross = (exit_px - pend["fill_price"]) / pend["fill_price"]
            else:
                gross = (pend["fill_price"] - exit_px) / pend["fill_price"]
            net_pct = round(gross * 100 - TAKER_FEE * 100, 5)

            etype = f"FORCED_CLOSE_{side.upper()}"
            events.append({
                "event_id":    _make_eid(pair, etype, open_ms),
                "run_utc":     run_utc,
                "pair":        pair,
                "event_type":  etype,
                "bar_open_ms": open_ms,
                "bar_open_utc": open_utc,
                "side":        side,
                "fill_price":  pend["fill_price"],
                "mid_at_fill": pend["mid_at_fill"],
                "exit_price":  round(exit_px, 8),
                "net_pct":     net_pct,
                "hold_bars":   bars_held,
                "notes":       f"entry_bar_ms={pend['bar_open_ms']}",
            })
            ps[f"pending_{side}"] = None
            ps["totals"]["forced_closes"] += 1
            ps["totals"]["realized_pnl_pct_sum"] = round(
                ps["totals"]["realized_pnl_pct_sum"] + net_pct, 6)

        # ── 2. New bid fill ──
        if ps["pending_bid"] is None and bar["low"] <= bid_limit:
            ps["pending_bid"] = {
                "fill_price":  round(bid_limit, 8),
                "mid_at_fill": round(mid, 8),
                "bar_open_ms": open_ms,
            }
            events.append({
                "event_id":    _make_eid(pair, "FILL_BID", open_ms),
                "run_utc":     run_utc,
                "pair":        pair,
                "event_type":  "FILL_BID",
                "bar_open_ms": open_ms,
                "bar_open_utc": open_utc,
                "side":        "bid",
                "fill_price":  round(bid_limit, 8),
                "mid_at_fill": round(mid, 8),
                "notes":       f"bar_low={bar['low']:.8f}",
            })
            ps["totals"]["fills"] += 1

        # ── 3. New ask fill ──
        if ps["pending_ask"] is None and bar["high"] >= ask_limit:
            ps["pending_ask"] = {
                "fill_price":  round(ask_limit, 8),
                "mid_at_fill": round(mid, 8),
                "bar_open_ms": open_ms,
            }
            events.append({
                "event_id":    _make_eid(pair, "FILL_ASK", open_ms),
                "run_utc":     run_utc,
                "pair":        pair,
                "event_type":  "FILL_ASK",
                "bar_open_ms": open_ms,
                "bar_open_utc": open_utc,
                "side":        "ask",
                "fill_price":  round(ask_limit, 8),
                "mid_at_fill": round(mid, 8),
                "notes":       f"bar_high={bar['high']:.8f}",
            })
            ps["totals"]["fills"] += 1

        # ── 4. Complete round-trip ──
        if ps["pending_bid"] is not None and ps["pending_ask"] is not None:
            entry_ms = min(ps["pending_bid"]["bar_open_ms"],
                           ps["pending_ask"]["bar_open_ms"])
            hold_bars = round((open_ms - entry_ms) / 3_600_000)
            net_pct = round(spread_pct - 0.0, 5)   # 0% maker on both legs

            events.append({
                "event_id":    _make_eid(pair, "COMPLETE_RT", open_ms),
                "run_utc":     run_utc,
                "pair":        pair,
                "event_type":  "COMPLETE_RT",
                "bar_open_ms": open_ms,
                "bar_open_utc": open_utc,
                "side":        "both",
                "fill_price":  ps["pending_bid"]["fill_price"],
                "mid_at_fill": ps["pending_bid"]["mid_at_fill"],
                "exit_price":  ps["pending_ask"]["fill_price"],
                "net_pct":     net_pct,
                "hold_bars":   hold_bars,
                "notes": (f"bid_ms={ps['pending_bid']['bar_open_ms']} "
                          f"ask_ms={ps['pending_ask']['bar_open_ms']}"),
            })
            ps["pending_bid"] = None
            ps["pending_ask"] = None
            ps["totals"]["complete_rts"] += 1
            ps["totals"]["realized_pnl_pct_sum"] = round(
                ps["totals"]["realized_pnl_pct_sum"] + net_pct, 6)

        # Advance cursor
        ps["last_processed_bar_open_ms"] = open_ms
        ps["last_processed_bar_close"] = bar["close"]

    return events


def _run_cohort_instance_on_bars(instance_id: str, ps: dict, completed: list[dict],
                                  run_utc: str, spread_pct: float) -> list[dict]:
    """Same init/new-bars/prev_close resolution as the main PAIRS loop in
    cmd_run, factored out (not shared code with that loop, by design — the
    original loop is left untouched) so cohort instruments can reuse one
    fetched `completed` bar list across all 6 width-variants of a symbol.
    `completed` bars are shared, read-mostly objects across those variants;
    the only field written back onto them (prev_close) is deterministic from
    the shared bar sequence itself, not from any instance's state, so this is
    safe to call repeatedly on the same list for each of a symbol's variants.
    """
    pair_is_first_run = ps["last_processed_bar_open_ms"] is None

    for i, bar in enumerate(completed):
        if i == 0 and "prev_close" not in bar:
            bar["prev_close"] = ps["last_processed_bar_close"]
        elif i > 0 and "prev_close" not in bar:
            bar["prev_close"] = completed[i - 1]["close"]

    if pair_is_first_run:
        seed_bar = completed[-1]
        ps["start_date_utc"] = run_utc
        ps["last_processed_bar_open_ms"] = seed_bar["open_time_ms"]
        ps["last_processed_bar_close"] = seed_bar["close"]
        print(f"  [{instance_id}] INIT seed bar: {ms_to_utc(seed_bar['open_time_ms'])}  "
              f"close={seed_bar['close']:.6f}  spread={spread_pct}%")
        return []

    last_ms = ps["last_processed_bar_open_ms"]
    new_bars = [b for b in completed if b["open_time_ms"] > last_ms]
    if not new_bars:
        return []

    first_new_ms = new_bars[0]["open_time_ms"]
    prev_in_window = [b for b in completed if b["open_time_ms"] < first_new_ms]
    if prev_in_window:
        new_bars[0]["prev_close"] = prev_in_window[-1]["close"]
    elif ps["last_processed_bar_close"] is not None:
        new_bars[0]["prev_close"] = ps["last_processed_bar_close"]
    else:
        new_bars = new_bars[1:]
        if not new_bars:
            return []

    for i in range(1, len(new_bars)):
        if new_bars[i].get("prev_close") is None:
            prev_in_completed = [b for b in completed if b["open_time_ms"] < new_bars[i]["open_time_ms"]]
            if prev_in_completed:
                new_bars[i]["prev_close"] = prev_in_completed[-1]["close"]

    events = process_pair_bars(instance_id, ps, new_bars, run_utc, spread_pct=spread_pct)
    for e in events:
        et = e["event_type"]
        if et.startswith("FILL"):
            print(f"    [{instance_id}] FILL   {et:<12} price={e['fill_price']:.6f}")
        elif et == "COMPLETE_RT":
            print(f"    [{instance_id}] RT     COMPLETE  net={e['net_pct']:.4f}%  hold={e['hold_bars']}h")
        elif et.startswith("FORCED"):
            print(f"    [{instance_id}] CLOSE  {et:<20} net={e['net_pct']:.4f}%  hold={e['hold_bars']}h")
    return events


def cmd_run_cohorts(state: dict, run_utc: str, all_events: list[dict],
                     pair_summaries: list[str]) -> None:
    """Process all 42 cohort instances. Fetches klines ONCE per unique
    underlying symbol (7 fetches, not 42) and fans that single fetch out to
    each symbol's 6 width-variants — each variant still has its own isolated
    `ps` dict (independent pending_bid/ask, totals, clock), so there is no
    shared mutable state between instances despite the shared bar data.
    Reads/writes only state["pairs"][<cohort instance_id>] — never touches
    a bare-symbol key (e.g. "MINAUSDT") used by the original 7 pairs.
    """
    by_symbol: dict[str, list[str]] = {}
    for instance_id, meta in COHORT_INSTRUMENTS.items():
        by_symbol.setdefault(meta["symbol"], []).append(instance_id)

    for symbol, instance_ids in by_symbol.items():
        print(f"\n[{symbol} cohort] fetching klines (shared across "
              f"{len(instance_ids)} width variants: {instance_ids})...")
        anchors = [state["pairs"][iid]["last_processed_bar_open_ms"] for iid in instance_ids]
        known_anchors = [a for a in anchors if a is not None]
        since_ms = (min(known_anchors) - 3_600_000) if known_anchors else None
        raw = fetch_klines(symbol, since_ms=since_ms)
        if not raw:
            for iid in instance_ids:
                pair_summaries.append(f"{iid}: fetch error — skipped")
            continue

        completed = [raw_to_bar(k) for k in raw[:-1]]
        if not completed:
            for iid in instance_ids:
                pair_summaries.append(f"{iid}: no completed bars")
            continue

        for instance_id in instance_ids:
            ps = state["pairs"][instance_id]
            if ps["suspended"]:
                pair_summaries.append(f"{instance_id}: SUSPENDED")
                continue
            spread_pct = COHORT_INSTRUMENTS[instance_id]["spread_pct"]
            events = _run_cohort_instance_on_bars(instance_id, ps, completed, run_utc, spread_pct)
            all_events.extend(events)

            t = ps["totals"]
            n_rts = t["complete_rts"] + t["forced_closes"]
            avg = t["realized_pnl_pct_sum"] / max(n_rts, 1)
            if ps["last_processed_bar_open_ms"] == completed[-1]["open_time_ms"] and not events and n_rts == 0 and t["fills"] == 0:
                pass  # first-run init already printed inline above
            pair_summaries.append(
                f"{instance_id}: fills={t['fills']} rt={t['complete_rts']} forced={t['forced_closes']} | "
                f"avg_net={avg:.4f}%/RT  total_net={t['realized_pnl_pct_sum']:.4f}%"
            )
        time.sleep(0.3)


def _run_hold_spread_instance_on_bars(instance_id: str, ps: dict, completed: list[dict],
                                       run_utc: str, spread_pct: float,
                                       max_hold_bars: int) -> list[dict]:
    """Same init/new-bars/prev_close resolution as _run_cohort_instance_on_bars
    (deliberately duplicated rather than shared, matching that function's own
    stated rationale — keeps each cohort runner independently auditable and
    leaves neither the original PAIRS loop nor the spread-width cohort loop
    touched). `completed` bars are shared, read-mostly across a symbol's 10
    width x hold variants; only `prev_close` is written back, deterministic
    from the shared bar sequence, so reuse across variants is safe.
    """
    pair_is_first_run = ps["last_processed_bar_open_ms"] is None

    for i, bar in enumerate(completed):
        if i == 0 and "prev_close" not in bar:
            bar["prev_close"] = ps["last_processed_bar_close"]
        elif i > 0 and "prev_close" not in bar:
            bar["prev_close"] = completed[i - 1]["close"]

    if pair_is_first_run:
        seed_bar = completed[-1]
        ps["start_date_utc"] = run_utc
        ps["last_processed_bar_open_ms"] = seed_bar["open_time_ms"]
        ps["last_processed_bar_close"] = seed_bar["close"]
        print(f"  [{instance_id}] INIT seed bar: {ms_to_utc(seed_bar['open_time_ms'])}  "
              f"close={seed_bar['close']:.6f}  spread={spread_pct}%  max_hold={max_hold_bars}h")
        return []

    last_ms = ps["last_processed_bar_open_ms"]
    new_bars = [b for b in completed if b["open_time_ms"] > last_ms]
    if not new_bars:
        return []

    first_new_ms = new_bars[0]["open_time_ms"]
    prev_in_window = [b for b in completed if b["open_time_ms"] < first_new_ms]
    if prev_in_window:
        new_bars[0]["prev_close"] = prev_in_window[-1]["close"]
    elif ps["last_processed_bar_close"] is not None:
        new_bars[0]["prev_close"] = ps["last_processed_bar_close"]
    else:
        new_bars = new_bars[1:]
        if not new_bars:
            return []

    for i in range(1, len(new_bars)):
        if new_bars[i].get("prev_close") is None:
            prev_in_completed = [b for b in completed if b["open_time_ms"] < new_bars[i]["open_time_ms"]]
            if prev_in_completed:
                new_bars[i]["prev_close"] = prev_in_completed[-1]["close"]

    events = process_pair_bars(instance_id, ps, new_bars, run_utc,
                                spread_pct=spread_pct, max_hold_bars=max_hold_bars)
    for e in events:
        et = e["event_type"]
        if et.startswith("FILL"):
            print(f"    [{instance_id}] FILL   {et:<12} price={e['fill_price']:.6f}")
        elif et == "COMPLETE_RT":
            print(f"    [{instance_id}] RT     COMPLETE  net={e['net_pct']:.4f}%  hold={e['hold_bars']}h")
        elif et.startswith("FORCED"):
            print(f"    [{instance_id}] CLOSE  {et:<20} net={e['net_pct']:.4f}%  hold={e['hold_bars']}h")
    return events


def cmd_run_hold_spread_cohort(state: dict, run_utc: str, all_events: list[dict],
                                pair_summaries: list[str]) -> None:
    """Process all 70 hold/spread-width matrix instances. Fetches klines ONCE
    per unique underlying symbol (7 fetches, not 70) and fans that single
    fetch out to each symbol's 10 width x hold variants — each variant still
    has its own isolated `ps` dict (independent pending_bid/ask, totals,
    clock), so there is no shared mutable state between instances despite the
    shared bar data. Reads/writes only state["pairs"][<matrix instance id>] —
    never touches a bare-symbol key or a spread-width-cohort key.
    """
    by_symbol: dict[str, list[str]] = {}
    for instance_id, meta in HOLD_SPREAD_INSTRUMENTS.items():
        by_symbol.setdefault(meta["symbol"], []).append(instance_id)

    for symbol, instance_ids in by_symbol.items():
        print(f"\n[{symbol} hold/spread matrix] fetching klines (shared across "
              f"{len(instance_ids)} width x hold variants)...")
        anchors = [state["pairs"][iid]["last_processed_bar_open_ms"] for iid in instance_ids]
        known_anchors = [a for a in anchors if a is not None]
        since_ms = (min(known_anchors) - 3_600_000) if known_anchors else None
        raw = fetch_klines(symbol, since_ms=since_ms)
        if not raw:
            for iid in instance_ids:
                pair_summaries.append(f"{iid}: fetch error — skipped")
            continue

        completed = [raw_to_bar(k) for k in raw[:-1]]
        if not completed:
            for iid in instance_ids:
                pair_summaries.append(f"{iid}: no completed bars")
            continue

        for instance_id in instance_ids:
            ps = state["pairs"][instance_id]
            if ps["suspended"]:
                pair_summaries.append(f"{instance_id}: SUSPENDED")
                continue
            meta = HOLD_SPREAD_INSTRUMENTS[instance_id]
            events = _run_hold_spread_instance_on_bars(
                instance_id, ps, completed, run_utc,
                spread_pct=meta["spread_pct"], max_hold_bars=meta["max_hold_bars"])
            all_events.extend(events)

            t = ps["totals"]
            n_rts = t["complete_rts"] + t["forced_closes"]
            avg = t["realized_pnl_pct_sum"] / max(n_rts, 1)
            pair_summaries.append(
                f"{instance_id}: fills={t['fills']} rt={t['complete_rts']} forced={t['forced_closes']} | "
                f"avg_net={avg:.4f}%/RT  total_net={t['realized_pnl_pct_sum']:.4f}%"
            )
        time.sleep(0.3)


def cmd_run_nil_spread_cohort(state: dict, run_utc: str, all_events: list[dict],
                               pair_summaries: list[str]) -> None:
    """Process NILUSDT's own 6-instance spread-width cohort. One kline fetch
    (NILUSDT only) fanned out to all 6 width variants, each with its own
    isolated `ps` dict. Reads/writes only state["pairs"][<NIL cohort id>] —
    never touches the bare "NILUSDT" live-pair key, the 7-pair cohort's keys,
    or the 70-instance matrix's keys.
    """
    instance_ids = list(NIL_SPREAD_COHORT_INSTRUMENTS.keys())
    print(f"\n[NILUSDT spread-width cohort] fetching klines (shared across "
          f"{len(instance_ids)} width variants: {instance_ids})...")
    anchors = [state["pairs"][iid]["last_processed_bar_open_ms"] for iid in instance_ids]
    known_anchors = [a for a in anchors if a is not None]
    since_ms = (min(known_anchors) - 3_600_000) if known_anchors else None
    raw = fetch_klines(NIL_SPREAD_COHORT_SYMBOL, since_ms=since_ms)
    if not raw:
        for iid in instance_ids:
            pair_summaries.append(f"{iid}: fetch error — skipped")
        return

    completed = [raw_to_bar(k) for k in raw[:-1]]
    if not completed:
        for iid in instance_ids:
            pair_summaries.append(f"{iid}: no completed bars")
        return

    for instance_id in instance_ids:
        ps = state["pairs"][instance_id]
        if ps["suspended"]:
            pair_summaries.append(f"{instance_id}: SUSPENDED")
            continue
        spread_pct = NIL_SPREAD_COHORT_INSTRUMENTS[instance_id]["spread_pct"]
        events = _run_cohort_instance_on_bars(instance_id, ps, completed, run_utc, spread_pct)
        all_events.extend(events)

        t = ps["totals"]
        n_rts = t["complete_rts"] + t["forced_closes"]
        avg = t["realized_pnl_pct_sum"] / max(n_rts, 1)
        pair_summaries.append(
            f"{instance_id}: fills={t['fills']} rt={t['complete_rts']} forced={t['forced_closes']} | "
            f"avg_net={avg:.4f}%/RT  total_net={t['realized_pnl_pct_sum']:.4f}%"
        )


def cmd_run_nil_hold_spread_cohort(state: dict, run_utc: str, all_events: list[dict],
                                    pair_summaries: list[str]) -> None:
    """Process NILUSDT's own 10-instance hold/spread-width matrix. One kline
    fetch (NILUSDT only) fanned out to all 10 hold x width variants, each
    with its own isolated `ps` dict. Reads/writes only
    state["pairs"][<NIL matrix id>] — never touches the bare "NILUSDT"
    live-pair key, the 7-pair 70-instance matrix's keys, or NIL's own
    spread-width cohort keys above.
    """
    instance_ids = list(NIL_HOLD_SPREAD_INSTRUMENTS.keys())
    print(f"\n[NILUSDT hold/spread matrix] fetching klines (shared across "
          f"{len(instance_ids)} hold x width variants)...")
    anchors = [state["pairs"][iid]["last_processed_bar_open_ms"] for iid in instance_ids]
    known_anchors = [a for a in anchors if a is not None]
    since_ms = (min(known_anchors) - 3_600_000) if known_anchors else None
    raw = fetch_klines(NIL_SPREAD_COHORT_SYMBOL, since_ms=since_ms)
    if not raw:
        for iid in instance_ids:
            pair_summaries.append(f"{iid}: fetch error — skipped")
        return

    completed = [raw_to_bar(k) for k in raw[:-1]]
    if not completed:
        for iid in instance_ids:
            pair_summaries.append(f"{iid}: no completed bars")
        return

    for instance_id in instance_ids:
        ps = state["pairs"][instance_id]
        if ps["suspended"]:
            pair_summaries.append(f"{instance_id}: SUSPENDED")
            continue
        meta = NIL_HOLD_SPREAD_INSTRUMENTS[instance_id]
        events = _run_hold_spread_instance_on_bars(
            instance_id, ps, completed, run_utc,
            spread_pct=meta["spread_pct"], max_hold_bars=meta["max_hold_bars"])
        all_events.extend(events)

        t = ps["totals"]
        n_rts = t["complete_rts"] + t["forced_closes"]
        avg = t["realized_pnl_pct_sum"] / max(n_rts, 1)
        pair_summaries.append(
            f"{instance_id}: fills={t['fills']} rt={t['complete_rts']} forced={t['forced_closes']} | "
            f"avg_net={avg:.4f}%/RT  total_net={t['realized_pnl_pct_sum']:.4f}%"
        )


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_status(state: dict) -> None:
    print(f"\nPaper Trade Status — {now_utc()}")
    print(f"  Start:    {state['meta']['start_date_utc'] or 'not yet initialised'}")
    print(f"  Last run: {state['meta']['last_run_utc'] or '—'}")
    for pair in PAIRS:
        ps = state["pairs"][pair]
        t = ps["totals"]
        suspended = " [SUSPENDED]" if ps["suspended"] else ""
        print(f"\n  {pair}{suspended}")
        print(f"    Start (own clock):   {ps.get('start_date_utc') or 'not yet initialised'}")
        print(f"    Last bar processed: {ms_to_utc(ps['last_processed_bar_open_ms']) if ps['last_processed_bar_open_ms'] else '—'}")
        print(f"    Pending bid:  {ps['pending_bid'] or 'none'}")
        print(f"    Pending ask:  {ps['pending_ask'] or 'none'}")
        print(f"    Totals: fills={t['fills']}  complete={t['complete_rts']}  forced={t['forced_closes']}  "
              f"realized_sum={t['realized_pnl_pct_sum']:.4f}%")


def _known_instance(pair: str) -> bool:
    return (pair in PAIRS or pair in COHORT_INSTRUMENTS or pair in HOLD_SPREAD_INSTRUMENTS
            or pair in NIL_SPREAD_COHORT_INSTRUMENTS or pair in NIL_HOLD_SPREAD_INSTRUMENTS)


def _all_known_instance_ids() -> list:
    return (PAIRS + list(COHORT_INSTRUMENTS) + list(HOLD_SPREAD_INSTRUMENTS)
            + list(NIL_SPREAD_COHORT_INSTRUMENTS) + list(NIL_HOLD_SPREAD_INSTRUMENTS))


def _resolve_instance_arg(raw: str) -> str:
    """CLI --suspend/--resume args used to be blindly .upper()'d in main(),
    harmless while every instance id was itself all-uppercase (the 7 live
    pairs, and the spread-width cohort's "SYMBOL-0.9"/"SYMBOL-1.0-FRESH"
    ids). The hold/spread-width matrix's "SYMBOL-1.0-3h" ids use a
    lowercase-h suffix (matching this cohort's naming spec), so a blind
    .upper() would turn a valid id into a non-existent "...-3H". Resolve
    case-insensitively instead: exact match first, then all-upper fallback
    for the older all-uppercase instance ids typed in lowercase.
    """
    if _known_instance(raw):
        return raw
    return raw.upper()


def cmd_suspend(state: dict, pair: str, dry_run: bool = False) -> None:
    if not _known_instance(pair):
        print(f"Unknown pair/instance: {pair}. Valid: {_all_known_instance_ids()}")
        return
    state["pairs"][pair]["suspended"] = True
    save_state(state, dry_run)
    print(f"{'[dry-run] ' if dry_run else ''}{pair} marked SUSPENDED.")


def cmd_resume(state: dict, pair: str, dry_run: bool = False) -> None:
    if not _known_instance(pair):
        print(f"Unknown pair/instance: {pair}. Valid: {_all_known_instance_ids()}")
        return
    state["pairs"][pair]["suspended"] = False
    save_state(state, dry_run)
    print(f"{'[dry-run] ' if dry_run else ''}{pair} resumed.")


def cmd_status_cohort(state: dict) -> None:
    """Status for the 42 spread-width cohort instances only, grouped by
    width — does not read or print anything from the original 7 PAIRS."""
    print(f"\nSpread-Width Cohort Status — {now_utc()}")
    print(f"  {len(COHORT_INSTRUMENTS)} instances = {len(COHORT_BASE_PAIRS)} pairs x {len(COHORT_WIDTH_GROUPS)} widths")
    for width in COHORT_WIDTH_GROUPS:
        label = "1.0% (fresh control)" if width == COHORT_FRESH_CONTROL_WIDTH else f"{width:.1f}%"
        print(f"\n  ── {label} cohort ──")
        for symbol in COHORT_BASE_PAIRS:
            iid = cohort_instance_id(symbol, width)
            ps = state["pairs"].get(iid)
            if ps is None:
                print(f"    {iid:<20} not yet initialised")
                continue
            t = ps["totals"]
            suspended = " [SUSPENDED]" if ps["suspended"] else ""
            note = f"  ⚠ {COHORT_NOTES[symbol]}" if symbol in COHORT_NOTES else ""
            print(f"    {iid:<20} start={ps.get('start_date_utc') or 'not yet initialised':<22} "
                  f"fills={t['fills']:>3} rt={t['complete_rts']:>3} forced={t['forced_closes']:>3} "
                  f"net={t['realized_pnl_pct_sum']:.4f}%{suspended}{note}")


def cmd_status_hold_spread(state: dict) -> None:
    """Status for the 70 hold/spread-width matrix instances only, grouped by
    hold then width — does not read or print anything from the original 7
    PAIRS or the 42-instance spread-width cohort."""
    print(f"\nHold/Spread-Width Matrix Status — {now_utc()}")
    print(f"  {len(HOLD_SPREAD_INSTRUMENTS)} instances = "
          f"{len(HOLD_SPREAD_BASE_PAIRS)} pairs x {len(HOLD_SPREAD_HOLDS)} holds x {len(HOLD_SPREAD_WIDTHS)} widths")
    for hold in HOLD_SPREAD_HOLDS:
        for width in HOLD_SPREAD_WIDTHS:
            print(f"\n  ── {hold}h hold / {width:.1f}% spread ──")
            for symbol in HOLD_SPREAD_BASE_PAIRS:
                iid = hold_spread_instance_id(symbol, width, hold)
                ps = state["pairs"].get(iid)
                if ps is None:
                    print(f"    {iid:<20} not yet initialised")
                    continue
                t = ps["totals"]
                suspended = " [SUSPENDED]" if ps["suspended"] else ""
                print(f"    {iid:<20} start={ps.get('start_date_utc') or 'not yet initialised':<22} "
                      f"fills={t['fills']:>3} rt={t['complete_rts']:>3} forced={t['forced_closes']:>3} "
                      f"net={t['realized_pnl_pct_sum']:.4f}%{suspended}")


def cmd_status_nil_cohort(state: dict) -> None:
    """Status for NIL's own 6-instance spread-width cohort only — does not
    read or print anything from the 7-pair cohort, the 70-instance matrix,
    or the live NILUSDT pair."""
    print(f"\nNILUSDT Spread-Width Cohort Status (separate from the 7-pair cohort) — {now_utc()}")
    print(f"  {len(NIL_SPREAD_COHORT_INSTRUMENTS)} instances = 1 pair (NILUSDT) x "
          f"{len(COHORT_WIDTHS) + 1} widths")
    for iid, meta in NIL_SPREAD_COHORT_INSTRUMENTS.items():
        ps = state["pairs"].get(iid)
        if ps is None:
            print(f"    {iid:<20} not yet initialised")
            continue
        t = ps["totals"]
        suspended = " [SUSPENDED]" if ps["suspended"] else ""
        print(f"    {iid:<20} {meta['width_label']:<22} start={ps.get('start_date_utc') or 'not yet initialised':<22} "
              f"fills={t['fills']:>3} rt={t['complete_rts']:>3} forced={t['forced_closes']:>3} "
              f"net={t['realized_pnl_pct_sum']:.4f}%{suspended}")


def cmd_status_nil_hold_spread(state: dict) -> None:
    """Status for NIL's own 10-instance hold/spread-width matrix only — does
    not read or print anything from the 7-pair matrix, the spread-width
    cohorts, or the live NILUSDT pair."""
    print(f"\nNILUSDT Hold/Spread-Width Matrix Status (separate from the 7-pair matrix) — {now_utc()}")
    print(f"  {len(NIL_HOLD_SPREAD_INSTRUMENTS)} instances = 1 pair (NILUSDT) x "
          f"{len(HOLD_SPREAD_HOLDS)} holds x {len(HOLD_SPREAD_WIDTHS)} widths")
    for hold in HOLD_SPREAD_HOLDS:
        for width in HOLD_SPREAD_WIDTHS:
            iid = hold_spread_instance_id(NIL_SPREAD_COHORT_SYMBOL, width, hold)
            ps = state["pairs"].get(iid)
            if ps is None:
                print(f"    {iid:<20} not yet initialised")
                continue
            t = ps["totals"]
            suspended = " [SUSPENDED]" if ps["suspended"] else ""
            print(f"    {iid:<20} start={ps.get('start_date_utc') or 'not yet initialised':<22} "
                  f"fills={t['fills']:>3} rt={t['complete_rts']:>3} forced={t['forced_closes']:>3} "
                  f"net={t['realized_pnl_pct_sum']:.4f}%{suspended}")


def cmd_run(state: dict, dry_run: bool = False) -> None:
    run_utc = now_utc()
    all_events: list[dict] = []
    pair_summaries: list[str] = []

    for pair in PAIRS:
        ps = state["pairs"][pair]
        # Each pair tracks its own seed/init independently, so a pair added
        # later (e.g. SFPUSDT joining an already-running MINA/KAVA state)
        # gets its own 30-day clock instead of inheriting the others' start.
        pair_is_first_run = ps["last_processed_bar_open_ms"] is None

        if ps["suspended"]:
            print(f"\n[{pair}] SUSPENDED — skipping")
            pair_summaries.append(f"{pair}: SUSPENDED")
            continue

        print(f"\n[{pair}] fetching klines...")
        # Use startTime when we have a last-bar anchor so gaps > 2 days are caught.
        # Subtract 1h from last_processed so the anchor bar itself is included
        # (needed for prev_close resolution on the first new bar).
        since_ms = (ps["last_processed_bar_open_ms"] - 3_600_000
                    if ps["last_processed_bar_open_ms"] is not None else None)
        raw = fetch_klines(pair, since_ms=since_ms)
        if not raw:
            pair_summaries.append(f"{pair}: fetch error — skipped")
            continue

        # Completed bars = all except last (last is in-progress or just-opened)
        completed = [raw_to_bar(k) for k in raw[:-1]]
        if not completed:
            pair_summaries.append(f"{pair}: no completed bars")
            continue

        # Build prev_close for each completed bar
        # Bar i's prev_close is bar i-1's close; bar 0 uses stored state
        for i, bar in enumerate(completed):
            if i == 0:
                bar["prev_close"] = ps["last_processed_bar_close"]  # may be None
            else:
                bar["prev_close"] = completed[i - 1]["close"]

        # ── Initialisation (this pair's first run) ──────────────────────────
        if pair_is_first_run:
            seed_bar = completed[-1]
            ps["start_date_utc"] = run_utc
            ps["last_processed_bar_open_ms"] = seed_bar["open_time_ms"]
            ps["last_processed_bar_close"] = seed_bar["close"]
            print(f"  INIT seed bar: {ms_to_utc(seed_bar['open_time_ms'])}  "
                  f"close={seed_bar['close']:.6f}")
            next_bar_utc = ms_to_utc(seed_bar["open_time_ms"] + 3_600_000)
            print(f"  First trading bar starts at: {next_bar_utc}")
            pair_summaries.append(f"{pair}: initialised — trading starts {next_bar_utc}")
            continue

        # ── Normal run: find new bars ────────────────────────────────────────
        last_ms = ps["last_processed_bar_open_ms"]
        new_bars = [b for b in completed if b["open_time_ms"] > last_ms]

        if not new_bars:
            print(f"  No new completed bars since {ms_to_utc(last_ms)}")
            pair_summaries.append(f"{pair}: no new bars")
            continue

        # Fix prev_close for first new bar
        first_new_ms = new_bars[0]["open_time_ms"]
        prev_in_window = [b for b in completed if b["open_time_ms"] < first_new_ms]
        if prev_in_window:
            new_bars[0]["prev_close"] = prev_in_window[-1]["close"]
        elif ps["last_processed_bar_close"] is not None:
            new_bars[0]["prev_close"] = ps["last_processed_bar_close"]
        else:
            # Can't determine mid for first new bar; skip it
            print(f"  WARNING: no prev_close for {ms_to_utc(first_new_ms)} — skipping that bar")
            new_bars = new_bars[1:]
            if not new_bars:
                pair_summaries.append(f"{pair}: skipped (no prev_close context)")
                continue

        # Ensure remaining new_bars have prev_close from the series
        for i in range(1, len(new_bars)):
            if new_bars[i].get("prev_close") is None:
                # Find prev bar in completed list
                prev_in_completed = [b for b in completed
                                     if b["open_time_ms"] < new_bars[i]["open_time_ms"]]
                if prev_in_completed:
                    new_bars[i]["prev_close"] = prev_in_completed[-1]["close"]

        print(f"  Processing {len(new_bars)} bar(s): "
              f"{ms_to_utc(new_bars[0]['open_time_ms'])} → "
              f"{ms_to_utc(new_bars[-1]['open_time_ms'])}")

        events = process_pair_bars(pair, ps, new_bars, run_utc)
        all_events.extend(events)

        # Print events inline
        for e in events:
            et = e["event_type"]
            if et.startswith("FILL"):
                print(f"    FILL   {et:<12} price={e['fill_price']:.6f}  mid={e['mid_at_fill']:.6f}")
            elif et == "COMPLETE_RT":
                print(f"    RT     COMPLETE  net={e['net_pct']:.4f}%  hold={e['hold_bars']}h")
            elif et.startswith("FORCED"):
                print(f"    CLOSE  {et:<20} net={e['net_pct']:.4f}%  hold={e['hold_bars']}h")

        t = ps["totals"]
        n_rts = t["complete_rts"] + t["forced_closes"]
        avg = t["realized_pnl_pct_sum"] / max(n_rts, 1)
        pair_summaries.append(
            f"{pair}: {len(new_bars)} bar(s) processed | "
            f"fills={t['fills']} rt={t['complete_rts']} forced={t['forced_closes']} | "
            f"avg_net={avg:.4f}%/RT  total_net={t['realized_pnl_pct_sum']:.4f}%"
        )
        time.sleep(0.3)

    # ── Spread-width cohort (42 instances, separate keys, see above) ────────
    cmd_run_cohorts(state, run_utc, all_events, pair_summaries)

    # ── Hold/spread-width matrix cohort (70 instances, separate keys) ───────
    cmd_run_hold_spread_cohort(state, run_utc, all_events, pair_summaries)

    # ── NILUSDT-only spread-width cohort (6 instances, separate keys) ───────
    cmd_run_nil_spread_cohort(state, run_utc, all_events, pair_summaries)

    # ── NILUSDT-only hold/spread-width matrix (10 instances, separate keys) ──
    cmd_run_nil_hold_spread_cohort(state, run_utc, all_events, pair_summaries)

    # ── Finalise ─────────────────────────────────────────────────────────────
    if state["meta"]["start_date_utc"] is None:
        state["meta"]["start_date_utc"] = run_utc  # earliest-ever run, for file-level display only

    state["meta"]["last_run_utc"] = run_utc
    # Additive, read-only-by-convention metadata for the dashboard/report to
    # resolve each cohort instance's symbol/width without importing this
    # module. Never overlaps with the "pairs" keys used by the original 7.
    state["cohort_meta"] = {
        "base_pairs": COHORT_BASE_PAIRS,
        "widths": COHORT_WIDTH_GROUPS,
        "instruments": COHORT_INSTRUMENTS,
        "notes": COHORT_NOTES,
    }
    # Same convention for the hold/spread-width matrix cohort. Never overlaps
    # with "pairs" keys used by the original 7 or the spread-width cohort.
    state["hold_spread_meta"] = {
        "base_pairs": HOLD_SPREAD_BASE_PAIRS,
        "widths": HOLD_SPREAD_WIDTHS,
        "holds": HOLD_SPREAD_HOLDS,
        "instruments": HOLD_SPREAD_INSTRUMENTS,
    }
    # Same convention for NIL's own two cohorts — never overlaps with any key
    # above (base_pairs is a single-element list, distinct dicts/instruments).
    state["nil_spread_cohort_meta"] = {
        "base_pairs": [NIL_SPREAD_COHORT_SYMBOL],
        "widths": COHORT_WIDTH_GROUPS,
        "instruments": NIL_SPREAD_COHORT_INSTRUMENTS,
    }
    state["nil_hold_spread_meta"] = {
        "base_pairs": [NIL_SPREAD_COHORT_SYMBOL],
        "widths": HOLD_SPREAD_WIDTHS,
        "holds": HOLD_SPREAD_HOLDS,
        "instruments": NIL_HOLD_SPREAD_INSTRUMENTS,
    }
    append_events(all_events, dry_run=dry_run)
    save_state(state, dry_run=dry_run)

    tag = " [DRY RUN]" if dry_run else ""
    print(f"\n{'─'*65}")
    print(f"Run complete{tag}: {run_utc}")
    for s in pair_summaries:
        print(f"  {s}")
    if any("initialised" not in s and "SUSPENDED" not in s for s in pair_summaries):
        print(f"\nRun: python src/paper_report.py  — for full P&L and AS report")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="MEXC paper trade runner")
    parser.add_argument("--dry-run",  action="store_true", help="Preview; no writes")
    parser.add_argument("--status",   action="store_true", help="Print state; no API calls")
    parser.add_argument("--status-cohort", action="store_true",
                        help="Print the 42-instance spread-width cohort, grouped by width; no API calls")
    parser.add_argument("--status-hold-spread", action="store_true",
                        help="Print the 70-instance hold/spread-width matrix cohort, grouped by hold+width; no API calls")
    parser.add_argument("--status-nil-cohort", action="store_true",
                        help="Print NILUSDT's own 6-instance spread-width cohort; no API calls")
    parser.add_argument("--status-nil-hold-spread", action="store_true",
                        help="Print NILUSDT's own 10-instance hold/spread-width matrix; no API calls")
    parser.add_argument("--suspend",  metavar="PAIR",      help="Suspend a pair or cohort instance (e.g. MINAUSDT, MINAUSDT-0.5, or MINAUSDT-1.0-3h)")
    parser.add_argument("--resume",   metavar="PAIR",      help="Resume a suspended pair or cohort instance")
    args = parser.parse_args()

    state = load_state()

    if args.status:
        cmd_status(state)
    elif args.status_cohort:
        cmd_status_cohort(state)
    elif args.status_hold_spread:
        cmd_status_hold_spread(state)
    elif args.status_nil_cohort:
        cmd_status_nil_cohort(state)
    elif args.status_nil_hold_spread:
        cmd_status_nil_hold_spread(state)
    elif args.suspend:
        cmd_suspend(state, _resolve_instance_arg(args.suspend), dry_run=args.dry_run)
    elif args.resume:
        cmd_resume(state, _resolve_instance_arg(args.resume), dry_run=args.dry_run)
    else:
        cmd_run(state, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
