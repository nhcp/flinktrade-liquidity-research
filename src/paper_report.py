"""
Paper trade P&L and adverse-selection report.

Reads data/paper_trade_events.csv and data/paper_trade_state.json.
Fetches current MEXC klines to fill in forward prices for AS analysis.

Adverse selection sign convention (same as analytics.py and backtest):
  BID fill (we bought):  AS = (px_future - fill_price) / fill_price
    → positive = price recovered (good); negative = continued down (bad)
  ASK fill (we sold):    AS = -(px_future - fill_price) / fill_price
    → positive = price fell after sale (good); negative = rose (bad)

Usage:
    python src/paper_report.py               # both pairs
    python src/paper_report.py --pair MINAUSDT
"""

import argparse
import csv
import json
import math
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PAIRS = ["MINAUSDT", "KAVAUSDT", "SFPUSDT"]
DATA_DIR = Path(__file__).parent.parent / "data"
STATE_FILE = DATA_DIR / "paper_trade_state.json"
EVENTS_FILE = DATA_DIR / "paper_trade_events.csv"
BASE_URL = "https://api.mexc.com/api/v3/klines"

SPREAD_PCT = 1.0
TAKER_FEE_PCT = 0.05
NOTIONAL_USDT = 50.0
DQ_AS_THRESH = -0.50 * SPREAD_PCT    # DQ if bid AS@1h drops below -0.50%
WATCH_BID_AS = -0.15 * SPREAD_PCT    # watch flag if bid AS@1h below -0.15%


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mean(vals: list[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


def _std(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return None
    mu = sum(vals) / len(vals)
    return math.sqrt(sum((v - mu) ** 2 for v in vals) / (len(vals) - 1))


def _pct(v: float | None, decimals: int = 4) -> str:
    return f"{v:.{decimals}f}%" if v is not None else "—"


# ── Data loading ──────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        print("State file not found — run paper_trade.py first.", file=sys.stderr)
        sys.exit(1)
    with open(STATE_FILE) as f:
        return json.load(f)


def load_events(pair_filter: str | None = None) -> list[dict]:
    if not EVENTS_FILE.exists():
        return []
    with open(EVENTS_FILE) as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if not pair_filter or r["pair"] == pair_filter]


def fetch_klines(pair: str, limit: int = 500) -> list[list]:
    """Fetch up to 500 recent 1h bars. Last one is in-progress and excluded from index."""
    url = f"{BASE_URL}?symbol={pair}&interval=60m&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-mm-papertrade/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        print(f"  ERROR fetching {pair}: {exc}", file=sys.stderr)
        return []


def build_kline_index(raw: list[list]) -> dict[int, float]:
    """Map open_time_ms → close_price for completed bars (all but last)."""
    return {int(k[0]): float(k[4]) for k in raw[:-1]}


# ── Adverse selection ─────────────────────────────────────────────────────────

def _signed_as(fill_price: float, side: str, future_close: float) -> float:
    raw = (future_close - fill_price) / fill_price
    return raw if side == "bid" else -raw


def compute_as(fill_events: list[dict], kline_idx: dict[int, float]) -> dict:
    """
    Returns {horizon_h: {"all": [...], "bid": [...], "ask": [...]}} for each horizon.
    Only includes observations where the future bar's close is available in kline_idx.
    """
    horizons = [1, 2, 4, 8, 12]
    result: dict[int, dict] = {h: {"all": [], "bid": [], "ask": []} for h in horizons}

    for fill in fill_events:
        if fill["event_type"] not in ("FILL_BID", "FILL_ASK"):
            continue
        try:
            fill_ms = int(fill["bar_open_ms"])
            fill_px = float(fill["fill_price"])
            side = fill["side"]
        except (KeyError, ValueError):
            continue

        for h in horizons:
            target_ms = fill_ms + h * 3_600_000
            future_close = kline_idx.get(target_ms)
            if future_close is None:
                continue
            as_val = _signed_as(fill_px, side, future_close)
            result[h]["all"].append(as_val)
            result[h][side].append(as_val)

    return result


# ── Report ────────────────────────────────────────────────────────────────────

def _elapsed_days(start_utc: str | None) -> float:
    if not start_utc:
        return 0.0
    start = datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - start).total_seconds() / 86400


def _decision_date(start_utc: str | None, window_days: int = 30) -> str | None:
    if not start_utc:
        return None
    start = datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
    from datetime import timedelta
    return (start + timedelta(days=window_days)).date().isoformat()


def report_pair(pair: str, state: dict, events: list[dict],
                kline_idx: dict[int, float], current_price: float | None) -> None:
    ps = state["pairs"].get(pair, {})
    totals = ps.get("totals", {})
    params = state["params"]

    fill_events = [e for e in events if e["event_type"] in ("FILL_BID", "FILL_ASK")]
    rt_events   = [e for e in events if e["event_type"] == "COMPLETE_RT"]
    fc_events   = [e for e in events if e["event_type"].startswith("FORCED_CLOSE")]
    all_rt      = rt_events + fc_events

    bid_fills = [e for e in fill_events if e["side"] == "bid"]
    ask_fills = [e for e in fill_events if e["side"] == "ask"]

    print(f"\n{'='*65}")
    print(f"  {pair}")
    if ps.get("suspended"):
        print(f"  STATUS: *** SUSPENDED ***")
    print(f"{'='*65}")

    start = ps.get("start_date_utc")
    elapsed = _elapsed_days(start)
    remaining = max(0, 30 - elapsed)
    decision = _decision_date(start)
    print(f"\n  Own clock:  started {start or 'not yet initialised'}")
    if start:
        print(f"              {elapsed:.1f} / 30 days elapsed  (remaining: {remaining:.1f} days)  "
              f"— decision date: {decision}")

    # ── Fill summary ──────────────────────────────────────────────────────────
    print(f"\n  Fills:")
    print(f"    Total:    {len(fill_events)}  ({len(bid_fills)} bid / {len(ask_fills)} ask)")
    print(f"    Complete round-trips:  {len(rt_events)}")
    print(f"    Forced closes:         {len(fc_events)}")
    if all_rt:
        fc_rate = len(fc_events) / len(all_rt)
        print(f"    Forced-close rate:     {fc_rate*100:.1f}%")

    # ── P&L ──────────────────────────────────────────────────────────────────
    if all_rt:
        rt_nets   = [float(e["net_pct"]) for e in all_rt  if e.get("net_pct") != ""]
        crt_nets  = [float(e["net_pct"]) for e in rt_events if e.get("net_pct") != ""]
        fc_nets   = [float(e["net_pct"]) for e in fc_events if e.get("net_pct") != ""]

        print(f"\n  P&L (realized):")
        if rt_nets:
            total_rt_pct = sum(rt_nets)
            total_rt_usdt = total_rt_pct / 100 * NOTIONAL_USDT * len(rt_nets)
            mu = _mean(rt_nets)
            sd = _std(rt_nets)
            rts_per_month = len(rt_nets) / max(_elapsed_days(state["meta"]["start_date_utc"]), 1) * 30
            sharpe = (mu / sd * math.sqrt(rts_per_month)) if (sd and sd > 1e-10) else float("nan")
            sharpe_str = f"{sharpe:.3f}" if not math.isnan(sharpe) else "n/a (<3 RTs)"
            print(f"    Mean net/RT (all):    {_pct(mu)}")
            print(f"    Total net (all):      {_pct(total_rt_pct, 2)}  ≈ ${total_rt_usdt:.2f} on ${NOTIONAL_USDT:.0f}/fill")
            print(f"    Monthly Sharpe:       {sharpe_str}")
        if crt_nets:
            print(f"    Mean net/complete RT: {_pct(_mean(crt_nets))}")
        if fc_nets:
            print(f"    Mean net/forced:      {_pct(_mean(fc_nets))}")

    # ── Open positions ────────────────────────────────────────────────────────
    pend_bid = ps.get("pending_bid")
    pend_ask = ps.get("pending_ask")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    if pend_bid or pend_ask:
        print(f"\n  Open positions (current price: {current_price:.6f} {pair[-4:] if pair else ''})"
              if current_price else "\n  Open positions:")
        if pend_bid:
            age_h = (now_ms - pend_bid["bar_open_ms"]) / 3_600_000
            if current_price:
                unreal = (current_price - pend_bid["fill_price"]) / pend_bid["fill_price"] * 100
                print(f"    Long  (bid): entry={pend_bid['fill_price']:.6f}  "
                      f"age={age_h:.1f}h  unrealized={_pct(unreal)}")
            else:
                print(f"    Long  (bid): entry={pend_bid['fill_price']:.6f}  age={age_h:.1f}h")
        if pend_ask:
            age_h = (now_ms - pend_ask["bar_open_ms"]) / 3_600_000
            if current_price:
                unreal = (pend_ask["fill_price"] - current_price) / pend_ask["fill_price"] * 100
                print(f"    Short (ask): entry={pend_ask['fill_price']:.6f}  "
                      f"age={age_h:.1f}h  unrealized={_pct(unreal)}")
            else:
                print(f"    Short (ask): entry={pend_ask['fill_price']:.6f}  age={age_h:.1f}h")
    else:
        print(f"\n  Open positions:  none")

    # ── Adverse selection ─────────────────────────────────────────────────────
    as_data = compute_as(fill_events, kline_idx)

    any_as = any(as_data[h]["all"] for h in [1, 2, 4])
    if any_as:
        print(f"\n  Adverse Selection (t+Nh forward returns after fill):")
        print(f"    {'Horizon':<8} {'N':>4}  {'Mean%':>9}  {'Std%':>8}  Gate")

        for h in [1, 2, 4, 8, 12]:
            vals = as_data[h]["all"]
            if not vals:
                continue
            mu = _mean(vals)
            sd = _std(vals)
            gate_note = ""
            if h == 1 and mu is not None:
                thresh = -0.15 * SPREAD_PCT
                dq     = -0.50 * SPREAD_PCT
                if mu < dq:
                    gate_note = f" *** DQ-FAIL: informed flow (thresh={dq:.3f}%)"
                elif mu < thresh:
                    gate_note = f" FAIL G4 (thresh={thresh:.3f}%)"
                else:
                    gate_note = " PASS G4"
            elif h == 4 and mu is not None:
                thresh = -0.30 * SPREAD_PCT
                gate_note = (" FAIL G5" if mu < thresh else " PASS G5") + f" (thresh={thresh:.3f}%)"
            sd_str = f"{sd:.4f}" if sd is not None else "—"
            print(f"    t+{h}h     {len(vals):>4}  {_pct(mu*100 if mu is not None else None, 4):>9}  "
                  f"{sd_str:>8}{gate_note}")

        # Bid-fill breakdown at t+1h — the MINA risk flag
        bid_as_1h = as_data[1]["bid"]
        ask_as_1h = as_data[1]["ask"]
        if bid_as_1h or ask_as_1h:
            print()
            if bid_as_1h:
                m = _mean(bid_as_1h)
                flag = ""
                if m is not None and m < DQ_AS_THRESH / 100:
                    flag = "  *** DQ-FAIL — suspend this pair immediately"
                elif m is not None and m < WATCH_BID_AS / 100:
                    flag = "  *** WATCH — bid adverse selection worsening"
                print(f"    Bid-fill AS t+1h:  {_pct(m*100 if m is not None else None, 4):>9}  "
                      f"(n={len(bid_as_1h)}){flag}")
            if ask_as_1h:
                m = _mean(ask_as_1h)
                print(f"    Ask-fill AS t+1h:  {_pct(m*100 if m is not None else None, 4):>9}  "
                      f"(n={len(ask_as_1h)})")
    else:
        print(f"\n  Adverse Selection:  insufficient data (need fills with ≥1 resolved forward bar)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper trade P&L and AS report")
    parser.add_argument("--pair", help="Restrict to one pair (e.g. MINAUSDT)")
    args = parser.parse_args()

    state = load_state()
    pairs = [args.pair.upper()] if args.pair else PAIRS
    all_events = load_events()

    print(f"\nPaper Trade Report  —  {now_utc()}")
    print(f"File first initialised: {state['meta'].get('start_date_utc') or 'not yet initialised'}")
    print(f"Last run:               {state['meta'].get('last_run_utc') or '—'}")
    print(f"(Each pair below tracks its own independent 30-day clock/decision date —")
    print(f" a pair added later than the others starts its own window from its own first run.)")

    # Fetch klines for forward-price lookup
    kline_indexes: dict[str, dict[int, float]] = {}
    current_prices: dict[str, float | None] = {}
    for pair in pairs:
        print(f"\n[{pair}] fetching klines for AS analysis...", end=" ", flush=True)
        raw = fetch_klines(pair, limit=500)
        if raw:
            kline_indexes[pair] = build_kline_index(raw)
            current_prices[pair] = float(raw[-1][4]) if raw else None
            print(f"{len(raw)} bars. Current price: {current_prices[pair]:.6f}")
        else:
            kline_indexes[pair] = {}
            current_prices[pair] = None
            print("fetch failed.")
        time.sleep(0.3)

    for pair in pairs:
        pair_events = [e for e in all_events if e["pair"] == pair]
        report_pair(pair, state, pair_events,
                    kline_indexes.get(pair, {}),
                    current_prices.get(pair))

    print(f"\n{'─'*65}")
    print("Decision rule after each pair's own 30 days:")
    print("  Each pair must independently maintain G4+G5 PASS through its own")
    print("  window, OR be suspended. Any pair's bid-fill AS at t+1h < -0.50% →")
    print("  suspend that pair immediately, e.g.:")
    print("    python src/paper_trade.py --suspend MINAUSDT")
    print("    python src/paper_trade.py --suspend SFPUSDT")
    print()


if __name__ == "__main__":
    main()
