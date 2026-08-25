"""
Toxic-flow stress test — original 7 live MEXC pairs (MINA/SFP/XYO/GOAT/XPR/
PIPPIN/S), using each pair's real historical bar data already on disk
(data/<PAIR>_1h.csv, as fetched by data_fetch.py at gate/onboarding time —
see per-pair mtimes printed below; this script does not refetch, so it is
"real historical fill data" as of that pull, not a fresh pull).

This is a diagnostic-only script. It reads data/<PAIR>_1h.csv, does NOT
touch paper_trade_state.json, paper_trade_events.csv, or any live pair's
clock/state, and does not write back to simulator.py.

Method (ported from crypto_mm_weex/src/toxic_flow_check.py, which itself
ported from ~/research/weex_screen/src/deep_validate.py::toxic_flow_stress
— same math): inject a synthetic 2-sigma/3-sigma/5-sigma permanent
price-level shock (computed from the pair's own realized bar-return std
dev) at a random point in the bar series, then re-run the strategy gate on
the whole post-shock series and report aggregate fill-adj monthly P&L, same
as this repo's own simulator.py::run_simulation. Reimplemented locally
(rather than calling simulator.run_simulation, which only loads bars from
disk by pair name) so that simulator.py itself is not touched — the fill/
forced-close/fee math below is a verbatim mirror of
simulator.py::run_simulation, just parameterized on an in-memory bars list
so shocked bars can be fed in.

This is a coarser proxy than a true "N round trips to recover" metric —
treat as a resilience signal, not a precise recovery-speed count (same
caveat carried by the WEEX version and the original weex_screen module).

Usage:
    python src/toxic_flow_check.py
    python src/toxic_flow_check.py --pair MINAUSDT
"""

import argparse
import random
from pathlib import Path

from simulator import Bar, load_bars, MAKER_FEE, TAKER_FEE, DATA_DIR

RANDOM_SEED = 42
MAX_HOLD_BARS = 3  # matches simulator.py::run_simulation's default max_hold_bars
PAIRS = ["MINAUSDT", "SFPUSDT", "XYOUSDT", "GOATUSDT", "XPRUSDT", "PIPPINUSDT", "SUSDT"]


def _bar_returns(bars: list[Bar]) -> list[float]:
    return [(bars[i].close - bars[i - 1].close) / bars[i - 1].close
            for i in range(1, len(bars)) if bars[i - 1].close > 0]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def simulate_bars(bars: list[Bar], spread_pct: float, max_hold_bars: int = MAX_HOLD_BARS) -> dict:
    """Verbatim mirror of simulator.py::run_simulation's fill/fee logic,
    parameterized on an in-memory bars list instead of loading from disk."""
    if len(bars) < 10:
        return {"error": "insufficient bars (<10)"}

    spread_half = spread_pct / 200.0
    pending_bid = None
    pending_ask = None
    round_trips = []
    total_fills = 0

    for i in range(1, len(bars)):
        curr = bars[i]
        mid = bars[i - 1].close
        bid_limit = mid * (1 - spread_half)
        ask_limit = mid * (1 + spread_half)

        if pending_bid is not None:
            age = i - pending_bid["bar_idx"]
            if age >= max_hold_bars:
                gross = (curr.close - pending_bid["fill_price"]) / pending_bid["fill_price"]
                net = gross - TAKER_FEE
                round_trips.append({"type": "forced_close", "net_pct": net * 100})
                pending_bid = None

        if pending_ask is not None:
            age = i - pending_ask["bar_idx"]
            if age >= max_hold_bars:
                gross = (pending_ask["fill_price"] - curr.close) / pending_ask["fill_price"]
                net = gross - TAKER_FEE
                round_trips.append({"type": "forced_close", "net_pct": net * 100})
                pending_ask = None

        if pending_bid is None and curr.low <= bid_limit:
            pending_bid = {"fill_price": bid_limit, "bar_idx": i}
            total_fills += 1

        if pending_ask is None and curr.high >= ask_limit:
            pending_ask = {"fill_price": ask_limit, "bar_idx": i}
            total_fills += 1

        if pending_bid is not None and pending_ask is not None:
            round_trips.append({"type": "complete", "net_pct": spread_pct})
            pending_bid = None
            pending_ask = None

    complete_rts = [r for r in round_trips if r["type"] == "complete"]
    forced_rts = [r for r in round_trips if r["type"] == "forced_close"]

    n_bars = len(bars) - 1
    days = n_bars / 24.0
    complete_per_month = len(complete_rts) / max(days, 1) * 30
    forced_per_month = len(forced_rts) / max(days, 1) * 30

    fills_in_complete = len(complete_rts) * 2
    fills_in_forced = len(forced_rts)
    total_fill_events = fills_in_complete + fills_in_forced
    forced_close_rate = fills_in_forced / max(total_fill_events, 1)

    mean_complete_net = _mean([r["net_pct"] for r in complete_rts])
    mean_forced_net = _mean([r["net_pct"] for r in forced_rts])

    adj_complete_monthly = complete_per_month * 0.50 * (mean_complete_net or 0)
    adj_forced_monthly = forced_per_month * (mean_forced_net or 0)
    fill_adj_net_monthly = adj_complete_monthly + adj_forced_monthly

    return {
        "total_fills": total_fills,
        "fill_adj_net_monthly_pct": round(fill_adj_net_monthly, 4),
        "forced_close_rate": round(forced_close_rate, 4),
    }


def toxic_flow_stress(bars: list[Bar], spread_pct: float, rng: random.Random) -> dict:
    returns = _bar_returns(bars)
    if len(returns) < 10:
        return {"error": "insufficient bar returns for sigma estimate"}
    mu = sum(returns) / len(returns)
    var = sum((r - mu) ** 2 for r in returns) / (len(returns) - 1)
    sigma = var ** 0.5

    out = {}
    for n_sigma in (2, 3, 5):
        shock_idx = rng.randint(len(bars) // 4, 3 * len(bars) // 4)
        shock_dir = rng.choice([1, -1])
        shock_pct = n_sigma * sigma * shock_dir

        shocked_bars = []
        for i, b in enumerate(bars):
            if i < shock_idx:
                shocked_bars.append(b)
            else:
                factor = 1 + shock_pct
                shocked_bars.append(Bar(
                    ts_ms=b.ts_ms,
                    open=b.open * factor, high=b.high * factor,
                    low=b.low * factor, close=b.close * factor,
                    vol_quote=b.vol_quote,
                ))

        r = simulate_bars(shocked_bars, spread_pct)
        if "error" in r:
            out[n_sigma] = {"error": r["error"]}
            continue

        out[n_sigma] = {
            "shock_pct": round(shock_pct * 100, 4),
            "post_shock_total_fills": r["total_fills"],
            "post_shock_fill_adj_monthly_pct": r["fill_adj_net_monthly_pct"],
            "post_shock_forced_close_rate": r["forced_close_rate"],
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", help="Single pair (e.g. MINAUSDT)")
    parser.add_argument("--spread", type=float, default=1.0)
    args = parser.parse_args()

    pairs = [args.pair] if args.pair else PAIRS

    print(f"Toxic-flow stress test — original 7 MEXC live pairs, this repo's own "
          f"simulator math (maker={MAKER_FEE*100:.2f}%, taker={TAKER_FEE*100:.2f}%)\n")

    summary = {}
    for pair in pairs:
        try:
            bars = load_bars(pair)
        except FileNotFoundError as e:
            print(f"[{pair}] {e}")
            continue

        import datetime
        mtime = (DATA_DIR / f"{pair}_1h.csv").stat().st_mtime
        as_of = datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc).strftime("%Y-%m-%d")

        rng = random.Random(RANDOM_SEED)
        tfs = toxic_flow_stress(bars, args.spread, rng)

        print(f"{'=' * 60}\n{pair}  (bars as of {as_of}, {len(bars)} bars)\n{'=' * 60}")
        positive_count = 0
        shock_results = {}
        for n_sigma, d in tfs.items():
            if "error" in d:
                print(f"  {n_sigma}-sigma: {d['error']}")
                shock_results[n_sigma] = "ERROR"
                continue
            pnl = d["post_shock_fill_adj_monthly_pct"]
            passed = pnl > 0
            if passed:
                positive_count += 1
            shock_results[n_sigma] = "PASS" if passed else "FAIL"
            print(f"  {n_sigma}-sigma shock ({d['shock_pct']}%): post-shock fill-adj monthly = "
                  f"{pnl:.4f}%, forced-close rate = {d['post_shock_forced_close_rate']:.4f}  "
                  f"[{shock_results[n_sigma]}]")
        all_positive = positive_count == 3
        print(f"  Positive across all 3 shock sizes? {'YES' if all_positive else f'NO ({positive_count}/3)'}")
        summary[pair] = (all_positive, shock_results)

    print(f"\n{'─'*60}")
    print("Toxic-flow stress summary — pass/fail per pair per shock size:")
    print(f"  {'PAIR':<12} {'2-sigma':<8} {'3-sigma':<8} {'5-sigma':<8} {'OVERALL'}")
    for pair, (all_positive, shocks) in summary.items():
        print(f"  {pair:<12} {shocks.get(2,'?'):<8} {shocks.get(3,'?'):<8} {shocks.get(5,'?'):<8} "
              f"{'RESILIENT' if all_positive else 'NOT RESILIENT'}")


if __name__ == "__main__":
    main()
