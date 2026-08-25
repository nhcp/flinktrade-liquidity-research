"""
Depth-realistic forced-close slippage diagnostic — the follow-up to
KILL_LOG.md's 2026-08-20 "Cost-model audit" entry, which flagged that
forced-close exits fill at exact bar-close price (zero slippage modeled)
and that the one available estimate (FlinkTrade DCA Bot's flat 0.05%/leg)
is explicitly calibrated for BTC/ETH/SOL futures — "dramatically more
liquid than MINA/SFP/XYO spot on MEXC" — and flagged as "likely a floor,
not an estimate." That entry recommended "MEXC L2 order-book depth
analysis" as the way to get an actual number. This script is that analysis.

Read-only, diagnostic-only: reads data/depth_snapshots.csv and
data/paper_trade_events.csv, writes only a report (appended to
KILL_LOG.md). Does NOT touch paper_trade_state.json, paper_trade_events.csv,
or any live pair's clock/quoting logic.

Method:
  1. For each live pair, use whatever order-book depth snapshots exist in
     data/depth_snapshots.csv (logged by depth_logger.py) to estimate a
     "walk the book" VWAP slippage for a NOTIONAL_USDT-sized forced-close
     market order (same $50 notional as paper_trade.py's per-fill sizing):
       - forced-close exit of a LONG (was filled on the bid) sells into the
         BID side of the book -> walk bids from best downward until $50
         notional is consumed, VWAP vs best_bid = bid-side slippage.
       - forced-close exit of a SHORT (was filled on the ask) buys against
         the ASK side -> walk asks from best upward, VWAP vs best_ask =
         ask-side slippage.
     Averaged across all available snapshots per pair (NOT time-matched to
     when each historical forced close actually happened — see caveat).
  2. Apply each pair's average bid-side/ask-side slippage to every
     FORCED_CLOSE_BID / FORCED_CLOSE_ASK event for that pair in
     paper_trade_events.csv, recompute net_pct, and report the delta vs.
     the originally recorded cumulative net_pct sum — same table shape as
     the 2026-08-20 DCA-rate diagnostic, so the two are directly comparable.

CRITICAL CAVEAT — read before trusting this number:
  Depth snapshots only exist from 2026-08-24 onward (PIPPINUSDT/NILUSDT)
  or from TODAY, 2026-08-25, onward (the other 6 live pairs, whose depth
  logging this task just turned on). Historical forced-close events go
  back to 2026-08-15. There is NO way to know what the order book actually
  looked like at each historical fill's exact moment — that data was never
  captured and cannot be reconstructed. What this script computes instead
  is: "if this pair's CURRENT/RECENT book depth is representative of its
  typical depth, here is what forced-close slippage would look like,
  applied uniformly to the historical event log as an estimate." This is
  the same structural limitation the DCA-rate diagnostic had (a borrowed,
  not-time-matched rate) — the improvement here is that the rate is now
  grounded in this exchange's real current depth for these specific pairs,
  not borrowed from unrelated, more-liquid BTC/ETH/SOL futures pairs. For
  MINA/SFP/XYO/GOAT/XPR/S, the estimate rests on a SINGLE current snapshot
  (depth logging for them started today) — treat those numbers as a rough
  order-of-magnitude read, not a stable average. PIPPIN/NIL have ~30
  hourly snapshots and are more robust. This will keep improving in place
  as depth_logger.py accumulates more history for all 8 pairs going
  forward; re-run this script periodically to tighten the estimate.

Usage:
    python src/slippage_model.py
"""

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
KILL_LOG = Path(__file__).parent.parent / "KILL_LOG.md"
SNAPSHOTS_FILE = DATA_DIR / "depth_snapshots.csv"
EVENTS_FILE = DATA_DIR / "paper_trade_events.csv"

NOTIONAL_USDT = 50.0  # matches paper_trade.py's NOTIONAL_USDT
TAKER_FEE = 0.0005     # matches paper_trade.py / simulator.py TAKER_FEE (0.05%)

LIVE_PAIRS = ["MINAUSDT", "SFPUSDT", "XYOUSDT", "GOATUSDT", "XPRUSDT", "PIPPINUSDT", "SUSDT", "NILUSDT"]


def _walk_book(levels: list[list[str]], notional_usdt: float) -> float | None:
    """levels: list of [px_str, qty_str], best price first. Returns VWAP
    price to fill notional_usdt, or None if book depth is insufficient."""
    remaining = notional_usdt
    cost = 0.0
    qty_filled = 0.0
    for px_s, qty_s in levels:
        px, qty = float(px_s), float(qty_s)
        level_notional = px * qty
        take_notional = min(level_notional, remaining)
        take_qty = take_notional / px
        cost += take_notional
        qty_filled += take_qty
        remaining -= take_notional
        if remaining <= 1e-9:
            break
    if qty_filled <= 0 or remaining > 1e-6:
        return None
    return cost / qty_filled


def load_snapshots() -> dict:
    """pair -> list of {best_bid, best_ask, bid_slip_pct, ask_slip_pct}"""
    out = defaultdict(list)
    if not SNAPSHOTS_FILE.exists():
        return out
    with open(SNAPSHOTS_FILE) as f:
        for row in csv.DictReader(f):
            pair = row["pair"]
            try:
                bids = json.loads(row["raw_bids_json"])
                asks = json.loads(row["raw_asks_json"])
                best_bid = float(row["best_bid_px"])
                best_ask = float(row["best_ask_px"])
            except (ValueError, json.JSONDecodeError):
                continue
            bid_vwap = _walk_book(bids, NOTIONAL_USDT)
            ask_vwap = _walk_book(asks, NOTIONAL_USDT)
            bid_slip = (best_bid - bid_vwap) / best_bid if bid_vwap is not None and best_bid > 0 else None
            ask_slip = (ask_vwap - best_ask) / best_ask if ask_vwap is not None and best_ask > 0 else None
            out[pair].append({"bid_slip_pct": bid_slip, "ask_slip_pct": ask_slip})
    return out


def average_slippage(snapshots: dict) -> dict:
    """pair -> {avg_bid_slip_pct, avg_ask_slip_pct, n_snapshots}"""
    out = {}
    for pair, snaps in snapshots.items():
        bid_vals = [s["bid_slip_pct"] for s in snaps if s["bid_slip_pct"] is not None]
        ask_vals = [s["ask_slip_pct"] for s in snaps if s["ask_slip_pct"] is not None]
        out[pair] = {
            "avg_bid_slip_pct": sum(bid_vals) / len(bid_vals) if bid_vals else None,
            "avg_ask_slip_pct": sum(ask_vals) / len(ask_vals) if ask_vals else None,
            "n_snapshots": len(snaps),
        }
    return out


def load_forced_close_events(pair: str) -> list[dict]:
    events = []
    with open(EVENTS_FILE) as f:
        for row in csv.DictReader(f):
            if row["pair"] != pair:
                continue
            if row["event_type"] not in ("FORCED_CLOSE_BID", "FORCED_CLOSE_ASK"):
                continue
            events.append(row)
    return events


def recompute_with_slippage(events: list[dict], avg_slip: dict) -> dict:
    orig_sum = 0.0
    adj_sum = 0.0
    flips = 0
    n_priced = 0
    n_unpriceable = 0

    for ev in events:
        orig_net = float(ev["net_pct"])
        orig_sum += orig_net

        side = ev["side"]
        fill_price = float(ev["fill_price"])
        exit_price = float(ev["exit_price"])

        slip = avg_slip["avg_bid_slip_pct"] if side == "bid" else avg_slip["avg_ask_slip_pct"]
        if slip is None:
            adj_sum += orig_net  # no depth data for this side -> can't adjust, use original
            n_unpriceable += 1
            continue
        n_priced += 1

        if side == "bid":  # long exit, sells into bids
            adj_exit = exit_price * (1 - slip)
            gross = (adj_exit - fill_price) / fill_price
        else:  # short exit, buys against asks
            adj_exit = exit_price * (1 + slip)
            gross = (fill_price - adj_exit) / fill_price
        adj_net = round(gross * 100 - TAKER_FEE * 100, 5)
        adj_sum += adj_net

        if (orig_net > 0) != (adj_net > 0):
            flips += 1

    return {
        "n_events": len(events),
        "n_priced": n_priced,
        "n_unpriceable": n_unpriceable,
        "orig_sum": round(orig_sum, 4),
        "adj_sum": round(adj_sum, 4),
        "delta": round(adj_sum - orig_sum, 4),
        "flips": flips,
    }


def main() -> None:
    snapshots = load_snapshots()
    avg_slip = average_slippage(snapshots)

    print("Depth-realistic slippage estimate per pair (from data/depth_snapshots.csv):\n")
    for pair in LIVE_PAIRS:
        s = avg_slip.get(pair, {"avg_bid_slip_pct": None, "avg_ask_slip_pct": None, "n_snapshots": 0})
        bid_s = f"{s['avg_bid_slip_pct']*100:.4f}%" if s["avg_bid_slip_pct"] is not None else "n/a"
        ask_s = f"{s['avg_ask_slip_pct']*100:.4f}%" if s["avg_ask_slip_pct"] is not None else "n/a"
        print(f"  {pair:<12} n_snapshots={s['n_snapshots']:<4} avg_bid_slip={bid_s:<10} avg_ask_slip={ask_s}")

    print(f"\n{'─'*90}")
    print("Forced-close P&L delta: original (bar-close, no slippage) vs. depth-realistic-slippage-adjusted\n")
    header = f"  {'Pair':<12}{'n forced':<10}{'orig sum':<12}{'depth-adj sum':<16}{'delta':<12}{'flips':<8}{'unpriceable'}"
    print(header)

    report_rows = []
    for pair in LIVE_PAIRS:
        events = load_forced_close_events(pair)
        s = avg_slip.get(pair, {"avg_bid_slip_pct": None, "avg_ask_slip_pct": None, "n_snapshots": 0})
        if not events:
            print(f"  {pair:<12}{'0':<10}(no forced-close events)")
            continue
        r = recompute_with_slippage(events, s)
        print(f"  {pair:<12}{r['n_events']:<10}{r['orig_sum']:<12}{r['adj_sum']:<16}{r['delta']:<12}"
              f"{r['flips']:<8}{r['n_unpriceable']}/{r['n_events']}")
        report_rows.append((pair, r, s))

    # ── Append report to KILL_LOG.md ──
    run_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    md = [f"\n---\n\n## {run_utc} — Depth-realistic forced-close slippage diagnostic\n\n",
          "Follow-up to the 2026-08-20 Cost-model audit entry above, which flagged DCA Bot's "
          "0.05%/leg as \"likely a floor, not an estimate\" and recommended MEXC order-book depth "
          "analysis as the way to get an actual number. This entry is that analysis, computed by "
          "`src/slippage_model.py` (read-only diagnostic; no live state touched).\n\n",
          "**Method:** for each live pair, walk the current order book (from `data/depth_snapshots.csv`, "
          f"logged by `depth_logger.py`) to find the VWAP fill price for a ${NOTIONAL_USDT:.0f} notional "
          "market order on the relevant side (bid side for a long's forced-close exit, ask side for a "
          "short's), average that slippage % across all available snapshots per pair, then apply it to "
          "every historical FORCED_CLOSE_BID/ASK event for that pair in `paper_trade_events.csv`.\n\n",
          "**Caveat — read before trusting this number:** depth snapshots only exist from 2026-08-24 "
          "onward (PIPPINUSDT/NILUSDT) or from today, 2026-08-25 (the other 6 pairs — this task just "
          "turned on their depth logging). Historical forced closes go back to 2026-08-15, and there is "
          "no way to know what the book looked like at each fill's actual moment. This applies a "
          "current/recent depth estimate uniformly to the historical log — the same structural "
          "limitation as the DCA-rate diagnostic (a not-time-matched rate), improved by being grounded "
          "in this exchange's real depth for these specific pairs rather than borrowed from unrelated, "
          "more-liquid BTC/ETH/SOL futures pairs. MINA/SFP/XYO/GOAT/XPR/S rest on a single current "
          "snapshot each (order-of-magnitude read only); PIPPIN/NIL have ~30 hourly snapshots "
          "(more robust). Re-run this script periodically as depth_logger.py accumulates more history.\n\n",
          "| Pair | n forced | orig realized_pnl_pct_sum | with depth-slippage | delta | win→loss flips | n snapshots |\n",
          "|---|---|---|---|---|---|---|\n"]
    for pair, r, s in report_rows:
        md.append(f"| {pair} | {r['n_events']} | {r['orig_sum']:+.4f}% | {r['adj_sum']:+.4f}% | "
                   f"{r['delta']:+.4f}pp | {r['flips']} | {s['n_snapshots']} |\n")
    md.append("\n**Action taken:** none — diagnostic only, `paper_trade_state.json` and "
               "`paper_trade_events.csv` untouched.\n")

    with open(KILL_LOG, "a") as f:
        f.writelines(md)
    print(f"\nAppended -> {KILL_LOG}")


if __name__ == "__main__":
    main()
