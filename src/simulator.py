"""
OHLCV-based market-maker simulator for MEXC 1h data.

Methodology:
- Mid-price = previous bar's close (no lookahead)
- Post bid at mid × (1 - spread/2), ask at mid × (1 + spread/2)
- BID FILL: bar's low ≤ posted bid (someone sold into our level)
- ASK FILL: bar's high ≥ posted ask (someone bought through our level)
- This OVERESTIMATES fill rate (ignores queue position); corrected by 50% haircut
- Forced close after max_hold_bars if other side not filled; uses taker fee 0.05%

Output: per-pair summary + data/<PAIR>_fills.csv for analytics.py

MEXC fees (0% maker, 0.05% taker — no volume requirement):
- Complete RT: 0% total fee (both sides are maker)
- Forced close: 0.05% on the exit leg only

Usage:
    python src/simulator.py
    python src/simulator.py --pair MINAUSDT --spread 0.8
    python src/simulator.py --spread 1.0 --spread 0.8 --spread 1.5  # sweep
"""

import argparse
import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

MAKER_FEE = 0.0000   # MEXC: 0% maker
TAKER_FEE = 0.0005   # MEXC: 0.05% taker
FILL_RATE_HAIRCUT = 0.50  # conservative: queue position unknown


@dataclass
class Bar:
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    vol_quote: float


@dataclass
class Fill:
    bar_idx: int
    ts_ms: int
    side: str          # "bid" or "ask"
    fill_price: float
    mid_at_fill: float
    future_closes: dict = field(default_factory=dict)  # {bars_ahead: close_price}


def load_bars(pair: str) -> list[Bar]:
    path = DATA_DIR / f"{pair}_1h.csv"
    if not path.exists():
        raise FileNotFoundError(f"No data for {pair} — run data_fetch.py first")
    bars = []
    with open(path) as f:
        for row in csv.DictReader(f):
            bars.append(Bar(
                ts_ms=int(row["open_time_ms"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                vol_quote=float(row["vol_quote"]),
            ))
    return bars


def run_simulation(pair: str, spread_pct: float, max_hold_bars: int = 3) -> dict:
    bars = load_bars(pair)
    if len(bars) < 10:
        return {"pair": pair, "spread_pct": spread_pct, "error": "insufficient bars (<10)"}

    spread_half = spread_pct / 200.0  # convert pct to fraction, then halve

    pending_bid: dict | None = None   # {fill_price, bar_idx, mid}
    pending_ask: dict | None = None

    fills: list[Fill] = []
    round_trips: list[dict] = []

    # Forward return horizons in bars (1h each)
    horizons = [1, 2, 4, 8, 12]

    for i in range(1, len(bars)):
        curr = bars[i]
        mid = bars[i - 1].close   # previous close as mid (no lookahead)

        bid_limit = mid * (1 - spread_half)
        ask_limit = mid * (1 + spread_half)

        # --- Check forced closes first ---
        if pending_bid is not None:
            age = i - pending_bid["bar_idx"]
            if age >= max_hold_bars:
                close_px = curr.close
                gross = (close_px - pending_bid["fill_price"]) / pending_bid["fill_price"]
                # 0% maker on entry, 0.05% taker on forced exit
                net = gross - TAKER_FEE
                round_trips.append({
                    "bar_idx": i,
                    "type": "forced_close",
                    "entry_side": "bid",
                    "gross_pct": gross * 100,
                    "net_pct": net * 100,
                    "hold_bars": age,
                })
                pending_bid = None

        if pending_ask is not None:
            age = i - pending_ask["bar_idx"]
            if age >= max_hold_bars:
                close_px = curr.close
                gross = (pending_ask["fill_price"] - close_px) / pending_ask["fill_price"]
                net = gross - TAKER_FEE
                round_trips.append({
                    "bar_idx": i,
                    "type": "forced_close",
                    "entry_side": "ask",
                    "gross_pct": gross * 100,
                    "net_pct": net * 100,
                    "hold_bars": age,
                })
                pending_ask = None

        # --- Check bid fill ---
        if pending_bid is None and curr.low <= bid_limit:
            pending_bid = {"fill_price": bid_limit, "bar_idx": i, "mid": mid}
            fill = Fill(bar_idx=i, ts_ms=curr.ts_ms, side="bid",
                        fill_price=bid_limit, mid_at_fill=mid)
            fills.append(fill)

        # --- Check ask fill ---
        if pending_ask is None and curr.high >= ask_limit:
            pending_ask = {"fill_price": ask_limit, "bar_idx": i, "mid": mid}
            fill = Fill(bar_idx=i, ts_ms=curr.ts_ms, side="ask",
                        fill_price=ask_limit, mid_at_fill=mid)
            fills.append(fill)

        # --- Check complete round-trip ---
        if pending_bid is not None and pending_ask is not None:
            # Both sides filled — spread captured, 0% maker on both sides
            hold_bars = i - min(pending_bid["bar_idx"], pending_ask["bar_idx"])
            gross = spread_pct  # % form
            net = gross - 0    # 0% maker, 0% maker = 0 fee on complete RT
            round_trips.append({
                "bar_idx": i,
                "type": "complete",
                "entry_side": "both",
                "gross_pct": gross,
                "net_pct": net,
                "hold_bars": hold_bars,
            })
            pending_bid = None
            pending_ask = None

    # --- Attach forward prices to fills ---
    for fill in fills:
        for h in horizons:
            target_idx = fill.bar_idx + h
            if target_idx < len(bars):
                fill.future_closes[h] = bars[target_idx].close

    # --- Compute summary statistics ---
    complete_rts = [r for r in round_trips if r["type"] == "complete"]
    forced_rts = [r for r in round_trips if r["type"] == "forced_close"]

    n_bars = len(bars) - 1  # usable bars (skip first, used as prev-close seed)
    days = n_bars / 24.0
    fills_per_month = len(fills) / max(days, 1) * 30
    complete_per_month = len(complete_rts) / max(days, 1) * 30
    forced_per_month = len(forced_rts) / max(days, 1) * 30

    # Forced close rate (fraction of fills that forced-close rather than complete RT)
    # Each complete RT uses 2 fills; each forced close uses 1
    fills_in_complete = len(complete_rts) * 2
    fills_in_forced = len(forced_rts)
    total_fill_events = fills_in_complete + fills_in_forced
    forced_close_rate = fills_in_forced / max(total_fill_events, 1)

    # P&L stats
    complete_net = [r["net_pct"] for r in complete_rts]
    forced_net = [r["net_pct"] for r in forced_rts]
    all_net = complete_net + forced_net

    mean_complete_net = _mean(complete_net)
    mean_forced_net = _mean(forced_net)
    mean_all_net = _mean(all_net)

    # Fill-rate-adjusted monthly P&L:
    # - complete RTs: scale by 50% fill rate haircut
    # - forced closes: they already happened; no haircut (they're realized outcomes)
    adj_complete_monthly = complete_per_month * FILL_RATE_HAIRCUT * (mean_complete_net or 0)
    adj_forced_monthly = forced_per_month * (mean_forced_net or 0)
    fill_adj_net_monthly = adj_complete_monthly + adj_forced_monthly

    # Sharpe from per-RT net returns (complete + forced)
    sharpe = float("nan")
    if len(all_net) >= 3:
        mu = mean_all_net or 0
        var = sum((r - mu) ** 2 for r in all_net) / (len(all_net) - 1)
        if var > 1e-12:
            std = math.sqrt(var)
            rts_per_month = len(all_net) / max(days, 1) * 30
            sharpe = mu / std * math.sqrt(rts_per_month)

    return {
        "pair": pair,
        "spread_pct": spread_pct,
        "n_bars": n_bars,
        "days": round(days, 1),
        "total_fills": len(fills),
        "fills_per_month": round(fills_per_month, 1),
        "complete_rts": len(complete_rts),
        "forced_rts": len(forced_rts),
        "complete_per_month": round(complete_per_month, 1),
        "forced_per_month": round(forced_per_month, 1),
        "forced_close_rate": round(forced_close_rate, 3),
        "mean_complete_net_pct": round(mean_complete_net, 4) if mean_complete_net is not None else None,
        "mean_forced_net_pct": round(mean_forced_net, 4) if mean_forced_net is not None else None,
        "mean_all_net_pct": round(mean_all_net, 4) if mean_all_net is not None else None,
        "fill_adj_net_monthly_pct": round(fill_adj_net_monthly, 4),
        "sharpe": round(sharpe, 3) if not math.isnan(sharpe) else float("nan"),
        "fills": fills,
    }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def check_gate(result: dict) -> dict:
    """Evaluate GATE.md criteria G1-G3 and G6 (G4/G5 come from analytics.py)."""
    if "error" in result:
        return {"error": result["error"], "overall": False}

    spread = result["spread_pct"]
    gate = {}

    # G1: fill count
    gate["G1_fills"] = result["total_fills"] >= 5

    # G2: mean net on complete RTs > 0.10%
    cnp = result.get("mean_complete_net_pct")
    gate["G2_complete_net"] = (cnp is not None) and cnp > 0.10

    # G3: fill-adj monthly net > 0
    gate["G3_fill_adj_net"] = result["fill_adj_net_monthly_pct"] > 0

    # G6: Sharpe ≥ 0.3
    sh = result.get("sharpe", float("nan"))
    gate["G6_sharpe"] = (not math.isnan(sh)) and sh >= 0.3

    # Disqualifying: forced close rate > 95%
    gate["DQ_forced_close_rate"] = result["forced_close_rate"] <= 0.95

    decided = [v for k, v in gate.items() if k != "overall" and v is not None]
    gate["overall"] = all(decided)
    return gate


def print_summary(result: dict, gate: dict) -> None:
    p = result["pair"]
    s = result["spread_pct"]
    if "error" in result:
        print(f"\n[{p} @ {s}%] ERROR: {result['error']}")
        return

    sharpe_str = f"{result['sharpe']:.3f}" if not math.isnan(result["sharpe"]) else "NaN"
    cnp = result["mean_complete_net_pct"]
    fnp = result["mean_forced_net_pct"]
    anp = result["mean_all_net_pct"]

    print(f"\n{'=' * 60}")
    print(f" {p}  |  spread={s}%  |  {result['days']} days  |  {result['n_bars']} bars")
    print(f"{'=' * 60}")
    print(f"  Total fills:          {result['total_fills']}")
    print(f"  Complete RTs:         {result['complete_rts']}  ({result['complete_per_month']:.1f}/month)")
    print(f"  Forced closes:        {result['forced_rts']}  ({result['forced_per_month']:.1f}/month)")
    print(f"  Forced close rate:    {result['forced_close_rate']*100:.1f}%  of fill events")
    print(f"  Mean net (complete):  {cnp:.4f}%  ← spread captured net of fees" if cnp is not None else "  Mean net (complete):  n/a (no complete RTs)")
    print(f"  Mean net (forced):    {fnp:.4f}%  ← actual forced-close P&L" if fnp is not None else "  Mean net (forced):    n/a")
    print(f"  Mean net (all RTs):   {anp:.4f}%" if anp is not None else "  Mean net (all RTs):   n/a")
    print(f"  Fill-adj monthly:     {result['fill_adj_net_monthly_pct']:.4f}%  (50% haircut on complete fills)")
    print(f"  Monthly Sharpe:       {sharpe_str}")

    print(f"\n  Gate results (G1-G3, G6 — G4/G5 from analytics.py):")
    for k, v in gate.items():
        if k == "overall":
            continue
        if v is True:
            status = "PASS"
        elif v is False:
            status = "FAIL"
        else:
            status = "PENDING"
        print(f"    {k}: {status}")


def save_fills_csv(pair: str, fills: list[Fill], spread_pct: float) -> None:
    out = DATA_DIR / f"{pair}_fills.csv"
    with open(out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ts_ms", "side", "fill_price", "mid_at_fill",
                         "px_1h", "px_2h", "px_4h", "px_8h", "px_12h"])
        for fill in fills:
            writer.writerow([
                fill.ts_ms,
                fill.side,
                fill.fill_price,
                fill.mid_at_fill,
                fill.future_closes.get(1, ""),
                fill.future_closes.get(2, ""),
                fill.future_closes.get(4, ""),
                fill.future_closes.get(8, ""),
                fill.future_closes.get(12, ""),
            ])
    print(f"  Fills saved → data/{pair}_fills.csv  (run analytics.py next)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", help="Single pair (e.g. MINAUSDT)")
    parser.add_argument("--spread", type=float, default=1.0,
                        help="Total spread %% to post (default 1.0)")
    parser.add_argument("--max-hold", type=int, default=3,
                        help="Bars before forced close (default 3 = 3 hours)")
    args = parser.parse_args()

    pairs = [args.pair] if args.pair else ["MINAUSDT", "KAVAUSDT"]
    all_gates: dict[str, dict] = {}

    for pair in pairs:
        try:
            result = run_simulation(pair, args.spread, args.max_hold)
        except FileNotFoundError as e:
            print(f"\n[{pair}] {e}")
            continue

        gate = check_gate(result)
        print_summary(result, gate)
        all_gates[pair] = gate

        if "fills" in result and result["fills"]:
            save_fills_csv(pair, result["fills"], args.spread)

    print(f"\n\n{'─'*60}")
    print(f"Gate summary (spread={args.spread}%, G1-G3/G6 only; G4/G5 pending analytics):")
    for pair, gate in all_gates.items():
        overall = "PARTIAL PASS" if gate.get("overall") else "FAIL / PENDING"
        print(f"  {pair}: {overall}")
    print("\nRun: python src/analytics.py  — to compute AS scores and evaluate G4/G5")


if __name__ == "__main__":
    main()
