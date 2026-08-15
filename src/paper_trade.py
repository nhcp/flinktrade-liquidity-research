"""
MEXC paper trade runner — MINA/USDT, KAVA/USDT, and SFP/USDT.

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

PAIRS = ["MINAUSDT", "KAVAUSDT", "SFPUSDT"]
BASE_URL = "https://api.mexc.com/api/v3/klines"
DATA_DIR = Path(__file__).parent.parent / "data"
STATE_FILE = DATA_DIR / "paper_trade_state.json"
EVENTS_FILE = DATA_DIR / "paper_trade_events.csv"

SPREAD_PCT = 1.0          # total spread; half posted each side
MAX_HOLD_BARS = 3         # hours before forced close
NOTIONAL_USDT = 50.0      # per fill (for dollar P&L tracking)
MAKER_FEE = 0.0000        # MEXC: 0% maker on limit orders that add liquidity
TAKER_FEE = 0.0005        # MEXC: 0.05% taker on forced close exit leg

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
        "pairs": {pair: _blank_pair_state() for pair in PAIRS},
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


def process_pair_bars(pair: str, ps: dict, bars: list[dict], run_utc: str) -> list[dict]:
    """
    Process a chronological sequence of new completed bars for one pair.

    Each bar must have a 'prev_close' key set by the caller.
    Modifies ps (pair state) in-place.
    Returns list of event dicts to be appended to the events CSV.
    """
    events: list[dict] = []
    spread_half = SPREAD_PCT / 200.0   # fraction, half-spread

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
            if bars_held < MAX_HOLD_BARS:
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
            net_pct = round(SPREAD_PCT - 0.0, 5)   # 0% maker on both legs

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


def cmd_suspend(state: dict, pair: str, dry_run: bool = False) -> None:
    if pair not in PAIRS:
        print(f"Unknown pair: {pair}. Valid: {PAIRS}")
        return
    state["pairs"][pair]["suspended"] = True
    save_state(state, dry_run)
    print(f"{'[dry-run] ' if dry_run else ''}{pair} marked SUSPENDED.")


def cmd_resume(state: dict, pair: str, dry_run: bool = False) -> None:
    if pair not in PAIRS:
        print(f"Unknown pair: {pair}. Valid: {PAIRS}")
        return
    state["pairs"][pair]["suspended"] = False
    save_state(state, dry_run)
    print(f"{'[dry-run] ' if dry_run else ''}{pair} resumed.")


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

    # ── Finalise ─────────────────────────────────────────────────────────────
    if state["meta"]["start_date_utc"] is None:
        state["meta"]["start_date_utc"] = run_utc  # earliest-ever run, for file-level display only

    state["meta"]["last_run_utc"] = run_utc
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
    parser.add_argument("--suspend",  metavar="PAIR",      help="Suspend a pair (e.g. MINAUSDT)")
    parser.add_argument("--resume",   metavar="PAIR",      help="Resume a suspended pair")
    args = parser.parse_args()

    state = load_state()

    if args.status:
        cmd_status(state)
    elif args.suspend:
        cmd_suspend(state, args.suspend.upper(), dry_run=args.dry_run)
    elif args.resume:
        cmd_resume(state, args.resume.upper(), dry_run=args.dry_run)
    else:
        cmd_run(state, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
