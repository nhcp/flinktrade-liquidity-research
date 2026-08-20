"""
Fetch MEXC public 1h klines (OHLCV) for MINA/USDT and KAVA/USDT.

Uses MEXC public REST API — no API key required.
Endpoint: GET https://api.mexc.com/api/v3/klines

Output: data/<PAIR>_1h.csv
Fields: open_time_ms, open, high, low, close, vol_base, vol_quote

Limitation: MEXC public klines cap at ~500 bars per symbol regardless of
startTime — provides approximately 20 calendar days of 1h data.

Usage:
    python src/data_fetch.py
    python src/data_fetch.py --pair MINAUSDT
"""

import argparse
import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PAIRS = ["MINAUSDT", "KAVAUSDT", "SFPUSDT", "XYOUSDT"]
BASE_URL = "https://api.mexc.com/api/v3/klines"
DATA_DIR = Path(__file__).parent.parent / "data"
RATE_LIMIT_SLEEP = 0.5  # MEXC public rate limit: generous, 0.5s is safe


def fetch_klines(pair: str) -> list[list]:
    """
    Fetch up to 500 1h bars from MEXC starting from the earliest available point.
    Returns list of raw kline arrays.
    """
    # Start from 90 days ago; API will return at most ~500 bars from its available history
    since_ms = int((datetime.now(timezone.utc).timestamp() - 90 * 86400) * 1000)
    url = f"{BASE_URL}?symbol={pair}&interval=60m&startTime={since_ms}&limit=500"
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-mm-research/2.0"})

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  HTTP error fetching {pair}: {e}", file=sys.stderr)
        return []

    if not isinstance(data, list):
        print(f"  Unexpected response for {pair}: {data}", file=sys.stderr)
        return []

    return data


def save_klines(pair: str, klines: list[list], out_path: Path) -> int:
    if not klines:
        return 0

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["open_time_ms", "open", "high", "low", "close",
                         "vol_base", "vol_quote"])
        for bar in klines:
            # MEXC kline format: [open_time_ms, open, high, low, close,
            #                      vol_base, close_time_ms, vol_quote]
            writer.writerow([
                int(bar[0]),    # open_time_ms
                str(bar[1]),    # open
                str(bar[2]),    # high
                str(bar[3]),    # low
                str(bar[4]),    # close
                str(bar[5]),    # vol_base
                str(bar[7]),    # vol_quote
            ])
    return len(klines)


def print_stats(pair: str, klines: list[list]) -> None:
    if not klines:
        print(f"  [{pair}] no data")
        return

    opens = [float(k[1]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    closes = [float(k[4]) for k in klines]
    vols = [float(k[7]) for k in klines]  # quote volume

    times = [int(k[0]) for k in klines]
    first_dt = datetime.fromtimestamp(times[0] / 1000, timezone.utc)
    last_dt = datetime.fromtimestamp(times[-1] / 1000, timezone.utc)
    span_days = (times[-1] - times[0]) / (86400 * 1000)

    hl_ranges_pct = [(h - l) / ((h + l) / 2) * 100 for h, l in zip(highs, lows) if h > 0 and l > 0]
    median_hl = sorted(hl_ranges_pct)[len(hl_ranges_pct) // 2] if hl_ranges_pct else 0
    mean_hl = sum(hl_ranges_pct) / len(hl_ranges_pct) if hl_ranges_pct else 0

    print(f"\n  [{pair}] stats:")
    print(f"    Bars:           {len(klines)} (1h each)")
    print(f"    Date range:     {first_dt.date()} → {last_dt.date()} ({span_days:.1f} days)")
    print(f"    Price range:    ${min(lows):.5f} – ${max(highs):.5f}")
    print(f"    Current price:  ${closes[-1]:.5f}")
    print(f"    Median H-L %:   {median_hl:.3f}%  (intrabar range; ≥ spread/2 needed for fills)")
    print(f"    Mean H-L %:     {mean_hl:.3f}%")
    print(f"    Mean vol/bar:   ${sum(vols)/len(vols):.0f} USDT/hour")
    print(f"    Total vol:      ${sum(vols):,.0f} USDT over period")

    if median_hl < 0.30:
        print(f"    WARNING: median H-L < 0.30% — most bars too tight for any spread to get fills")
    elif median_hl < 0.50:
        print(f"    NOTE: median H-L {median_hl:.3f}% — tight spread (≤0.8%) needed to generate fills")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", help="Single MEXC pair to fetch (e.g. MINAUSDT)")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pairs = [args.pair] if args.pair else PAIRS

    for pair in pairs:
        print(f"\nFetching {pair} from MEXC...")
        klines = fetch_klines(pair)

        if not klines:
            print(f"  {pair}: no data returned")
            continue

        out_path = DATA_DIR / f"{pair}_1h.csv"
        count = save_klines(pair, klines, out_path)
        print(f"  {pair}: {count} bars → {out_path.name}")
        print_stats(pair, klines)

        if pairs.index(pair) < len(pairs) - 1:
            time.sleep(RATE_LIMIT_SLEEP)

    print("\nDone. Run src/simulator.py next.")


if __name__ == "__main__":
    main()
