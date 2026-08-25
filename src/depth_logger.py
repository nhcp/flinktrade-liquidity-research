"""
Passive order-book depth snapshot logger — MEXC public API.

Pure logging, no strategy logic, no fills, no gate criteria. Pulls a top-of-book
depth snapshot for a fixed pair list and appends to data/depth_snapshots.csv.
Does NOT touch paper_trade_state.json, paper_trade_events.csv, or any live
pair's trading state.

Purpose: let a human later join depth imbalance against forced-close event
timestamps (paper_trade_events.csv) to check correlation. No such analysis is
performed here.

Run once per hour (cron or manual), same cadence as paper_trade.py.

Usage:
    python src/depth_logger.py
"""

import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PAIRS = ["PIPPINUSDT", "NILUSDT", "MINAUSDT", "SFPUSDT", "XYOUSDT", "GOATUSDT", "XPRUSDT", "SUSDT"]
DEPTH_LIMIT = 20  # top N levels each side
BASE_URL = "https://api.mexc.com/api/v3/depth"
DATA_DIR = Path(__file__).parent.parent / "data"
OUT_FILE = DATA_DIR / "depth_snapshots.csv"
FIELDS = [
    "snapshot_utc", "snapshot_ms", "pair",
    "best_bid_px", "best_bid_qty", "best_ask_px", "best_ask_qty",
    "bid_qty_sum_top20", "ask_qty_sum_top20",
    "mexc_timestamp_ms", "raw_bids_json", "raw_asks_json",
]


def fetch_depth(pair: str, limit: int = DEPTH_LIMIT) -> dict | None:
    url = f"{BASE_URL}?symbol={pair}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-mm-depth-logger/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        print(f"  ERROR fetching depth for {pair}: {exc}", file=sys.stderr)
        return None


def ensure_header() -> None:
    if not OUT_FILE.exists():
        with open(OUT_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def log_snapshot(pair: str, snap_utc: str, snap_ms: int) -> None:
    data = fetch_depth(pair)
    if not data or "bids" not in data or "asks" not in data:
        print(f"  {pair}: no usable depth data")
        return
    bids = data["bids"]
    asks = data["asks"]
    row = {
        "snapshot_utc": snap_utc,
        "snapshot_ms": snap_ms,
        "pair": pair,
        "best_bid_px": bids[0][0] if bids else "",
        "best_bid_qty": bids[0][1] if bids else "",
        "best_ask_px": asks[0][0] if asks else "",
        "best_ask_qty": asks[0][1] if asks else "",
        "bid_qty_sum_top20": sum(float(b[1]) for b in bids),
        "ask_qty_sum_top20": sum(float(a[1]) for a in asks),
        "mexc_timestamp_ms": data.get("timestamp", ""),
        "raw_bids_json": json.dumps(bids),
        "raw_asks_json": json.dumps(asks),
    }
    with open(OUT_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
    print(f"  {pair}: logged (best_bid={row['best_bid_px']} best_ask={row['best_ask_px']})")


def main() -> None:
    ensure_header()
    now = datetime.now(timezone.utc)
    snap_utc = now.isoformat().replace("+00:00", "Z")
    snap_ms = int(now.timestamp() * 1000)
    print(f"Depth snapshot run — {snap_utc}")
    for pair in PAIRS:
        log_snapshot(pair, snap_utc, snap_ms)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
