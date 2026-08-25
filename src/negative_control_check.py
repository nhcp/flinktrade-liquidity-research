"""
Weekly negative-control re-check for all live MEXC pairs.

Diagnostic-only. Fetches a fresh kline pull per pair (does NOT read/write
paper_trade_state.json or paper_trade_events.csv, does NOT touch any live
pair's clock), then checks the real strategy's fill-adjusted monthly net
against two constructed controls on that same fresh data — same method
description as GATE.md/PAPER_TRADE.md's prose (originally run ad hoc,
per-pair, at onboarding time in an external thread with no locatable
artifact in this repo — see weex_screen/src/deep_validate.py's provenance
note). This module is the first actual implementation living in this repo,
intended to run on a schedule so every live pair gets re-checked on an
ongoing basis instead of only once at onboarding.

Two controls, each averaged over N_CONTROL_TRIALS random seeds:
  a. random-entry control: same number of "trades" as the real strategy,
     placed at uniformly random bar indices/sides instead of the
     strategy's actual bid/ask trigger levels, exit after MAX_HOLD_BARS at
     that bar's close (taker fee both legs — random entries can't rest as
     maker).
  b. shuffled-price control: the bar close-price series is randomly
     permuted (breaking autocorrelation/mean-reversion), synthetic
     intrabar noise added so fills remain possible on the flat shuffled
     OHLC, then the real strategy logic is re-run on the shuffled series.

Uses simulate_bars() from toxic_flow_check.py (itself a verbatim mirror of
simulator.py::run_simulation's fill/fee math) rather than duplicating that
math a third time.

Usage:
    python src/negative_control_check.py
    python src/negative_control_check.py --pair MINAUSDT
"""

import argparse
import random
import sys
import time
import urllib.request
import json
from datetime import datetime, timezone
from pathlib import Path

from simulator import Bar
from toxic_flow_check import simulate_bars, MAX_HOLD_BARS

SPREAD_PCT = 1.0  # matches paper_trade.py's live spread for the original 7 pairs

DATA_DIR = Path(__file__).parent.parent / "data"
DOCS_DIR = Path(__file__).parent.parent / "docs"
OUT_FILE = DOCS_DIR / "NEGATIVE_CONTROL_WEEKLY.md"

BASE_URL = "https://api.mexc.com/api/v3/klines"
N_CONTROL_TRIALS = 30
RANDOM_SEED = 42

# Live pairs as of 2026-08-25: original 7 (KAVAUSDT suspended 2026-08-15,
# excluded) plus NILUSDT (onboarded 2026-08-23). See PAPER_TRADE.md status
# header. This list is intentionally independent of paper_trade.py's PAIRS
# / cohort structures — it does not read or affect those.
LIVE_PAIRS = ["MINAUSDT", "SFPUSDT", "XYOUSDT", "GOATUSDT", "XPRUSDT", "PIPPINUSDT", "SUSDT", "NILUSDT"]


def fetch_fresh_bars(pair: str, limit: int = 500) -> list[Bar]:
    since_ms = int((datetime.now(timezone.utc).timestamp() - 90 * 86400) * 1000)
    url = f"{BASE_URL}?symbol={pair}&interval=60m&startTime={since_ms}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-mm-negctrl/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    if not isinstance(data, list):
        raise RuntimeError(f"unexpected klines response for {pair}: {data}")
    return [
        Bar(ts_ms=int(k[0]), open=float(k[1]), high=float(k[2]), low=float(k[3]),
            close=float(k[4]), vol_quote=float(k[7]))
        for k in data
    ]


def negative_controls(bars: list[Bar], spread_pct: float, real_fill_adj_monthly: float,
                       real_fills: int, rng: random.Random) -> dict:
    n_bars = len(bars)

    # --- Control A: random-entry, same fill count as real strategy ---
    random_entry_results = []
    for _ in range(N_CONTROL_TRIALS):
        pnl = []
        for _ in range(real_fills):
            i = rng.randint(1, n_bars - MAX_HOLD_BARS - 1)
            side = rng.choice(["bid", "ask"])
            entry_px = bars[i].close
            exit_px = bars[i + MAX_HOLD_BARS].close
            if entry_px <= 0:
                continue
            gross = (exit_px - entry_px) / entry_px if side == "bid" else (entry_px - exit_px) / entry_px
            net = gross - 0.0005  # taker in and out; generous vs. random entries' real cost
            pnl.append(net * 100)
        if pnl:
            days = (n_bars - 1) / 24.0
            per_month = len(pnl) / max(days, 1) * 30
            random_entry_results.append(per_month * (sum(pnl) / len(pnl)))
    random_entry_monthly = sum(random_entry_results) / len(random_entry_results) if random_entry_results else 0.0

    # --- Control B: shuffled-price series, real strategy logic re-run ---
    closes = [b.close for b in bars]
    shuffled_results = []
    for _ in range(N_CONTROL_TRIALS):
        shuffled_closes = closes[:]
        rng.shuffle(shuffled_closes)
        shuffled_bars = []
        for i in range(n_bars):
            c = shuffled_closes[i]
            noise = abs(rng.gauss(0, 0.003)) * c
            shuffled_bars.append(Bar(
                ts_ms=bars[i].ts_ms, open=c, high=c + noise,
                low=max(c - noise, 1e-12), close=c, vol_quote=bars[i].vol_quote,
            ))
        r = simulate_bars(shuffled_bars, spread_pct)
        if "error" not in r:
            shuffled_results.append(r["fill_adj_net_monthly_pct"])
    shuffled_monthly = sum(shuffled_results) / len(shuffled_results) if shuffled_results else 0.0

    return {
        "real_fill_adj_monthly": real_fill_adj_monthly,
        "random_entry_monthly": round(random_entry_monthly, 4),
        "shuffled_price_monthly": round(shuffled_monthly, 4),
        "beats_random_entry": real_fill_adj_monthly > random_entry_monthly,
        "beats_shuffled_price": real_fill_adj_monthly > shuffled_monthly,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", help="Single pair (e.g. MINAUSDT)")
    parser.add_argument("--spread", type=float, default=SPREAD_PCT)
    args = parser.parse_args()

    pairs = [args.pair] if args.pair else LIVE_PAIRS
    run_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    lines = [f"\n---\n\n## {run_utc} — weekly negative-control re-run\n",
              "Fresh MEXC kline pull per pair (not the static data_fetch.py CSVs), "
              f"spread={args.spread}%, {N_CONTROL_TRIALS} trials/control, seed={RANDOM_SEED}.\n"]
    print(f"Weekly negative-control re-run — {run_utc}\n")

    results = []
    for pair in pairs:
        try:
            bars = fetch_fresh_bars(pair)
        except Exception as e:
            print(f"[{pair}] fetch error: {e}")
            lines.append(f"- **{pair}**: fetch error: {e}\n")
            continue

        real = simulate_bars(bars, args.spread)
        if "error" in real:
            print(f"[{pair}] {real['error']}")
            lines.append(f"- **{pair}**: {real['error']}\n")
            continue

        rng = random.Random(RANDOM_SEED)
        nc = negative_controls(bars, args.spread, real["fill_adj_net_monthly_pct"], real["total_fills"], rng)

        verdict = "PASS (beats both controls)" if (nc["beats_random_entry"] and nc["beats_shuffled_price"]) else "FLAG"
        print(f"{pair}: real={nc['real_fill_adj_monthly']:.4f}%  random-entry={nc['random_entry_monthly']:.4f}% "
              f"(beats: {nc['beats_random_entry']})  shuffled-price={nc['shuffled_price_monthly']:.4f}% "
              f"(beats: {nc['beats_shuffled_price']})  -> {verdict}")
        lines.append(
            f"- **{pair}**: real={nc['real_fill_adj_monthly']:.4f}%/mo, "
            f"random-entry={nc['random_entry_monthly']:.4f}%/mo (beats: {nc['beats_random_entry']}), "
            f"shuffled-price={nc['shuffled_price_monthly']:.4f}%/mo (beats: {nc['beats_shuffled_price']}) "
            f"-> **{verdict}**\n"
        )
        results.append((pair, nc))
        time.sleep(0.3)

    flags = [p for p, nc in results if not (nc["beats_random_entry"] and nc["beats_shuffled_price"])]
    summary = f"\nSummary: {len(results) - len(flags)}/{len(results)} pairs beat both negative controls this run."
    if flags:
        summary += f" Flagged: {', '.join(flags)}."
    print(summary)
    lines.append(summary + "\n")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not OUT_FILE.exists()
    with open(OUT_FILE, "a") as f:
        if is_new:
            f.write("# Weekly Negative-Control Re-Run Log\n\nAppend-only. Each run re-checks every "
                    "live pair's real fill-adjusted monthly net against a random-entry control and a "
                    "shuffled-price control, on a fresh kline pull. Does not backfill history that "
                    "predates this log — the first entry below is the first run.\n")
        f.writelines(lines)
    print(f"\nAppended -> {OUT_FILE}")


if __name__ == "__main__":
    main()
