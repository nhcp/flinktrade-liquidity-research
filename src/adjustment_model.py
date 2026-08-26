"""
Per-pair live-P&L adjustment estimator — combines two real-data corrections
that paper_trade.py's raw touch-rule tracking doesn't apply:

  1. Forced-close slippage (reuses slippage_model.py's already-verified
     walk-the-book VWAP logic against data/depth_snapshots.csv — not
     duplicated here, imported directly).
  2. Fill-probability (NEW here): replaces simulator.py's flat, unexplained
     FILL_RATE_HAIRCUT = 0.50 with a per-pair estimate derived from real
     data — resting book depth (qty-at-level, from depth_snapshots.csv)
     versus typical trading turnover (vol_quote, from data/<PAIR>_1h.csv).

HONEST LIMITATION — read before trusting fill_prob as "real queue position":
  This is NOT a true order-queue simulation. An L2 depth snapshot shows
  aggregate resting quantity at a price level, not individual order age or
  rank within that level — there is no way to know, from public REST data,
  where in the queue a hypothetical new order would actually sit. What this
  estimates instead is a coarser, defensible proxy: "how much resting size
  sits at the touched level, relative to how much real volume typically
  trades through that pair per bar." More resting depth relative to typical
  turnover -> lower probability a new order clears the queue within a bar.
  More turnover relative to depth -> higher probability. This is a "better
  than an arbitrary flat 50%" estimate, not "true queue position" — treat
  it accordingly. It also assumes a new order joins at the BACK of the
  visible queue (the conservative assumption, since we don't know better).

Method for fill_prob(pair, side):
    p = avg_bar_volume_quote / (avg_bar_volume_quote + avg_resting_notional_at_level)
  i.e. a saturating ratio: if a bar's typical turnover vastly exceeds the
  resting size at the level, most of that resting queue turns over within
  the bar (p -> high); if resting size vastly exceeds typical turnover, a
  new order at the back of the queue is unlikely to clear within the bar
  (p -> low). Clipped to [0.05, 0.95] — the data available here (often a
  single depth snapshot per pair) does not support claiming near-certainty
  in either direction, so both extremes are deliberately capped.

A complete round-trip needs BOTH legs to independently clear their queues:
  p_complete = p_fill_bid * p_fill_ask
This directly replaces FILL_RATE_HAIRCUT (0.50) wherever a pair-specific,
data-derived complete-RT probability is needed.

Depth-data confidence is reported alongside every number this module
produces — most live pairs have only 1-2 depth snapshots as of the date
this module was built (depth logging for them just started); only
PIPPINUSDT/NILUSDT have a deeper history (~30 hourly snapshots). Confidence
labels: 0 snapshots = "no depth data", 1-4 = "thin", 5-19 = "moderate",
20+ = "robust". This will strengthen automatically as depth_logger.py
accumulates more history — no code change needed for that improvement.

Usage:
    python src/adjustment_model.py                # print current estimate, all live pairs
    python src/adjustment_model.py --pair MINAUSDT
"""

import csv
from pathlib import Path

from slippage_model import load_snapshots, average_slippage, NOTIONAL_USDT as SLIPPAGE_NOTIONAL_USDT

DATA_DIR = Path(__file__).parent.parent / "data"

FILL_PROB_NOTIONAL_USDT = 50.0  # same $ sizing as paper_trade.py's NOTIONAL_USDT
FILL_PROB_FLOOR = 0.05
FILL_PROB_CEIL = 0.95
LEGACY_DEFAULT_FILL_PROB = 0.50  # fallback only if a pair has zero depth data at all

LIVE_PAIRS = ["MINAUSDT", "SFPUSDT", "XYOUSDT", "GOATUSDT", "XPRUSDT", "PIPPINUSDT", "SUSDT", "NILUSDT"]


def confidence_label(n_snapshots: int) -> str:
    if n_snapshots == 0:
        return "no depth data"
    if n_snapshots < 5:
        return f"thin ({n_snapshots} snapshot{'s' if n_snapshots != 1 else ''})"
    if n_snapshots < 20:
        return f"moderate ({n_snapshots} snapshots)"
    return f"robust ({n_snapshots} snapshots)"


def _avg_resting_notional(snapshots: dict, pair: str) -> dict:
    """Returns {'bid': avg_notional_or_None, 'ask': avg_notional_or_None} from
    depth_snapshots.csv's best_bid/best_ask qty*px, per pair."""
    snaps_file = DATA_DIR / "depth_snapshots.csv"
    bid_notionals, ask_notionals = [], []
    if snaps_file.exists():
        with open(snaps_file) as f:
            for row in csv.DictReader(f):
                if row["pair"] != pair:
                    continue
                try:
                    bp, bq = float(row["best_bid_px"]), float(row["best_bid_qty"])
                    ap, aq = float(row["best_ask_px"]), float(row["best_ask_qty"])
                except (ValueError, KeyError):
                    continue
                bid_notionals.append(bp * bq)
                ask_notionals.append(ap * aq)
    return {
        "bid": sum(bid_notionals) / len(bid_notionals) if bid_notionals else None,
        "ask": sum(ask_notionals) / len(ask_notionals) if ask_notionals else None,
    }


def _avg_bar_volume_quote(pair: str) -> float | None:
    path = DATA_DIR / f"{pair}_1h.csv"
    if not path.exists():
        return None
    vols = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                vols.append(float(row["vol_quote"]))
            except (ValueError, KeyError):
                continue
    return sum(vols) / len(vols) if vols else None


def estimate_fill_probability(pair: str) -> dict:
    """Returns {'fill_prob_bid', 'fill_prob_ask', 'fill_prob_complete',
    'n_snapshots', 'avg_bar_volume_quote', 'confidence'}."""
    snapshots = load_snapshots()
    n_snapshots = len(snapshots.get(pair, []))
    resting = _avg_resting_notional(snapshots, pair)
    avg_vol = _avg_bar_volume_quote(pair)

    def _p(resting_notional):
        if resting_notional is None or avg_vol is None:
            return LEGACY_DEFAULT_FILL_PROB
        p = avg_vol / (avg_vol + resting_notional) if (avg_vol + resting_notional) > 0 else LEGACY_DEFAULT_FILL_PROB
        return max(FILL_PROB_FLOOR, min(FILL_PROB_CEIL, p))

    p_bid = _p(resting["bid"])
    p_ask = _p(resting["ask"])
    return {
        "fill_prob_bid": round(p_bid, 4),
        "fill_prob_ask": round(p_ask, 4),
        "fill_prob_complete": round(p_bid * p_ask, 4),
        "n_snapshots": n_snapshots,
        "avg_bar_volume_quote": round(avg_vol, 2) if avg_vol is not None else None,
        "avg_resting_notional_bid": round(resting["bid"], 2) if resting["bid"] is not None else None,
        "avg_resting_notional_ask": round(resting["ask"], 2) if resting["ask"] is not None else None,
        "confidence": confidence_label(n_snapshots),
    }


def estimate_pair_adjustment(pair: str) -> dict:
    """Combined slippage + fill-probability estimate for one pair. Reuses
    slippage_model.py's already-verified snapshot/slippage functions rather
    than recomputing that logic here."""
    snapshots = load_snapshots()
    slip = average_slippage(snapshots).get(
        pair, {"avg_bid_slip_pct": None, "avg_ask_slip_pct": None, "n_snapshots": 0})
    fp = estimate_fill_probability(pair)
    return {
        "pair": pair,
        "avg_bid_slip_pct": slip["avg_bid_slip_pct"],
        "avg_ask_slip_pct": slip["avg_ask_slip_pct"],
        "fill_prob_bid": fp["fill_prob_bid"],
        "fill_prob_ask": fp["fill_prob_ask"],
        "fill_prob_complete": fp["fill_prob_complete"],
        "n_snapshots": fp["n_snapshots"],
        "avg_bar_volume_quote": fp["avg_bar_volume_quote"],
        "confidence": fp["confidence"],
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair")
    args = parser.parse_args()
    pairs = [args.pair] if args.pair else LIVE_PAIRS

    print("Per-pair adjustment model — current estimate (fill-probability is a "
          "coarse proxy, NOT true queue position; see module docstring)\n")
    for pair in pairs:
        a = estimate_pair_adjustment(pair)
        bid_s = f"{a['avg_bid_slip_pct']*100:.4f}%" if a["avg_bid_slip_pct"] is not None else "n/a"
        ask_s = f"{a['avg_ask_slip_pct']*100:.4f}%" if a["avg_ask_slip_pct"] is not None else "n/a"
        print(f"  {pair:<12} confidence={a['confidence']:<20} "
              f"slip(bid/ask)={bid_s}/{ask_s}  "
              f"fill_prob(bid/ask/complete)={a['fill_prob_bid']}/{a['fill_prob_ask']}/{a['fill_prob_complete']}  "
              f"avg_bar_vol=${a['avg_bar_volume_quote']}")


if __name__ == "__main__":
    main()
