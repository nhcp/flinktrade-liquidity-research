"""
Adverse selection analytics for MEXC 1h OHLCV simulation.

Reads fills CSVs produced by simulator.py and computes fill-conditional
forward returns at each horizon (t+1h, t+2h, t+4h, t+8h, t+12h).

Adverse selection sign convention:
    BID fill (we bought):  AS = (px_future - fill_price) / fill_price
        → negative means price fell after we bought (bad for us)
    ASK fill (we sold):    AS = -(px_future - fill_price) / fill_price
        → negative means price rose after we sold (bad for us)

Gate thresholds (from GATE.md):
    G4: AS at t+1h  > -0.15 × spread_pct  (i.e. > -0.15% for 1% spread)
    G5: AS at t+4h  > -0.30 × spread_pct  (i.e. > -0.30% for 1% spread)
    DISQUALIFY: AS at t+1h < -0.50 × spread_pct  (informed flow dominant)

Usage:
    python src/analytics.py
    python src/analytics.py --pair MINAUSDT --spread 1.0
"""

import argparse
import csv
import math
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
PAIRS = ["MINAUSDT", "KAVAUSDT", "SFPUSDT"]


def load_fills(pair: str) -> list[dict]:
    path = DATA_DIR / f"{pair}_fills.csv"
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def signed_as(fill: dict, horizon_h: int) -> float | None:
    """
    Compute signed adverse-selection return for a fill at a given horizon.
    Negative = price moved against our position direction.
    """
    key = f"px_{horizon_h}h"
    if not fill.get(key):
        return None
    px_future = float(fill[key])
    fill_price = float(fill["fill_price"])
    if fill_price == 0:
        return None

    raw = (px_future - fill_price) / fill_price

    # BID fill: we bought — negative if price fell
    # ASK fill: we sold  — negative if price rose
    return raw if fill["side"] == "bid" else -raw


def stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "std": None, "pct25": None,
                "median": None, "pct75": None}
    n = len(values)
    mu = sum(values) / n
    var = sum((v - mu) ** 2 for v in values) / n if n > 1 else 0.0
    std = math.sqrt(var)
    sv = sorted(values)
    return {
        "n": n,
        "mean": round(mu * 100, 5),
        "std": round(std * 100, 5),
        "pct25": round(sv[int(n * 0.25)] * 100, 5),
        "median": round(sv[n // 2] * 100, 5),
        "pct75": round(sv[int(n * 0.75)] * 100, 5),
    }


def gate_label(mean_pct: float | None, spread_pct: float, horizon_h: int) -> str:
    if mean_pct is None:
        return "PENDING (no data)"
    threshold_g4 = -0.15 * spread_pct   # G4: t+1h
    threshold_g5 = -0.30 * spread_pct   # G5: t+4h
    hard_fail = -0.50 * spread_pct      # disqualifying

    threshold = threshold_g4 if horizon_h == 1 else threshold_g5

    if mean_pct < hard_fail:
        return (f"DQ-FAIL (informed flow: {mean_pct:.4f}% < {hard_fail:.4f}%)")
    if mean_pct < threshold:
        return f"FAIL ({mean_pct:.4f}% < {threshold:.4f}%)"
    return f"PASS ({mean_pct:.4f}% ≥ {threshold:.4f}%)"


def analyze_pair(pair: str, spread_pct: float) -> dict:
    fills = load_fills(pair)
    if not fills:
        print(f"\n[{pair}] No fills file — run simulator.py first")
        return {}

    horizons = [1, 2, 4, 8, 12]
    as_by_h: dict[int, list[float]] = {h: [] for h in horizons}

    for fill in fills:
        for h in horizons:
            r = signed_as(fill, h)
            if r is not None:
                as_by_h[h].append(r)

    bid_fills = [f for f in fills if f["side"] == "bid"]
    ask_fills = [f for f in fills if f["side"] == "ask"]

    print(f"\n{'=' * 65}")
    print(f" Adverse Selection Analysis: {pair}  |  spread={spread_pct}%")
    print(f" Total fills: {len(fills)}  ({len(bid_fills)} bid, {len(ask_fills)} ask)")
    print(f"{'=' * 65}")
    print(f"  {'Horizon':<10} {'N':>4} {'Mean%':>9} {'Std%':>8} {'p25%':>9} "
          f"{'Median%':>9} {'p75%':>9}  Gate")
    print(f"  {'─'*80}")

    results: dict[int, dict] = {}
    for h in horizons:
        st = stats(as_by_h[h])
        label = ""
        if h in (1, 4):
            label = gate_label(st.get("mean"), spread_pct, h)
        print(f"  t+{h}h       {st['n']:>4}  {str(st.get('mean','—')):>9}  "
              f"{str(st.get('std','—')):>8}  {str(st.get('pct25','—')):>9}  "
              f"{str(st.get('median','—')):>9}  {str(st.get('pct75','—')):>9}  {label}")
        results[h] = st

    # Bid vs ask breakdown at t+1h (diagnose asymmetric AS)
    if bid_fills and ask_fills:
        bid_1h = [signed_as(f, 1) for f in bid_fills if signed_as(f, 1) is not None]
        ask_1h = [signed_as(f, 1) for f in ask_fills if signed_as(f, 1) is not None]
        print()
        if bid_1h:
            m = sum(bid_1h) / len(bid_1h)
            print(f"  Bid-fill AS (t+1h): mean = {m*100:.4f}%  (n={len(bid_1h)})")
        if ask_1h:
            m = sum(ask_1h) / len(ask_1h)
            print(f"  Ask-fill AS (t+1h): mean = {m*100:.4f}%  (n={len(ask_1h)})")

    g4_pass = "PASS" in gate_label(results.get(1, {}).get("mean"), spread_pct, 1)
    g5_pass = "PASS" in gate_label(results.get(4, {}).get("mean"), spread_pct, 4)
    dq = "DQ-FAIL" in gate_label(results.get(1, {}).get("mean"), spread_pct, 1)

    return {
        "pair": pair,
        "total_fills": len(fills),
        "as_1h": results.get(1, {}).get("mean"),
        "as_2h": results.get(2, {}).get("mean"),
        "as_4h": results.get(4, {}).get("mean"),
        "as_8h": results.get(8, {}).get("mean"),
        "as_12h": results.get(12, {}).get("mean"),
        "G4_pass": g4_pass and not dq,
        "G5_pass": g5_pass,
        "DQ_informed_flow": dq,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", help="Single pair to analyze")
    parser.add_argument("--spread", type=float, default=1.0,
                        help="Spread %% used in simulation (for gate thresholds)")
    args = parser.parse_args()

    pairs = [args.pair] if args.pair else PAIRS
    all_results = []

    for pair in pairs:
        r = analyze_pair(pair, args.spread)
        if r:
            all_results.append(r)

    print(f"\n\n{'─'*65}")
    print("Adverse Selection Gate Summary (G4 = t+1h, G5 = t+4h):")
    print(f"  {'Pair':<14} {'AS@1h%':>9} {'G4':>6} {'AS@4h%':>9} {'G5':>6} {'DQ?':>5}")
    print(f"  {'─'*55}")

    full_pass: list[str] = []
    disqualified: list[str] = []
    for r in all_results:
        g4 = "PASS" if r.get("G4_pass") else "FAIL"
        g5 = "PASS" if r.get("G5_pass") else "FAIL"
        dq = "YES" if r.get("DQ_informed_flow") else "no"
        as1 = f"{r['as_1h']:.4f}" if r.get("as_1h") is not None else "—"
        as4 = f"{r['as_4h']:.4f}" if r.get("as_4h") is not None else "—"
        print(f"  {r['pair']:<14} {as1:>9} {g4:>6} {as4:>9} {g5:>6} {dq:>5}")
        if r.get("G4_pass") and r.get("G5_pass") and not r.get("DQ_informed_flow"):
            full_pass.append(r["pair"])
        if r.get("DQ_informed_flow"):
            disqualified.append(r["pair"])

    print(f"\n  Pairs passing G4 + G5:     {full_pass or 'none'}")
    print(f"  Pairs disqualified (DQ):   {disqualified or 'none'}")
    print()
    print("Update GATE.md results section with these AS scores.")
    print("Final pass requires ALL of G1-G6 on BOTH pairs.")


if __name__ == "__main__":
    main()
