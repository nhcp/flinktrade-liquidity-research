# Crypto MM MEXC — Research Thread
## Started: 2026-08-14

**Hypothesis (Bianchi, Babiak & Dickerson 2022, JBF):**
Short-term reversal / liquidity-provision returns concentrate in low-volume crypto pairs.
Compensation for adverse-selection risk is highest in thin markets. The edge turns
negative after fees on high-volume venues, surviving only where maker fees are zero.

---

## Differences from Previous Thread (crypto_mm, Kraken proxy)

The prior thread (commit 3170fb7) used Kraken trade-level data as a PROXY for MEXC,
then evaluated results under hypothetical MEXC fees. That is methodologically weak:
Kraken and MEXC have different participant profiles, order book depth, and microstructure.

This thread uses REAL MEXC data for the EXACT pairs we would trade.

| Dimension | Prior thread | This thread |
|---|---|---|
| Data source | Kraken public API | MEXC public API |
| Data format | Tick-level trades | 1h OHLCV klines |
| Fill detection | Trade-crossing (tick) | OHLCV range crossing (1h bar) |
| Fee regime | Simulated MEXC fee on Kraken data | Actual MEXC fee on MEXC data |
| Pairs | MINA/USD, KAVA/USD (Kraken symbols) | MINA/USDT, KAVA/USDT (MEXC symbols) |

---

## Task 1: Pair and Venue Verification

### MEXC Pair Confirmation (API-verified, 2026-08-14)

```
GET https://api.mexc.com/api/v3/exchangeInfo?symbol=MINAUSDT
→ status: 1 (TRADING), isSpotTradingAllowed: True, quoteAsset: USDT

GET https://api.mexc.com/api/v3/exchangeInfo?symbol=KAVAUSDT
→ status: 1 (TRADING), isSpotTradingAllowed: True, quoteAsset: USDT
```

### MEXC 24h Volume (2026-08-14)

| Pair | Last Price | 24h Vol (base) | 24h Vol (USDT) |
|---|---|---|---|
| MINA/USDT | $0.03939 | 1,585,598 MINA | $63,005 |
| KAVA/USDT | $0.04069 | 1,616,825 KAVA | $65,624 |

Both pairs are legitimately low-volume (~$63-65K/day USDT). For reference, BTC/USDT
on MEXC trades ~$500M/day. These pairs are ~4 orders of magnitude thinner.

### MEXC Fee Schedule

**Public MEXC spot fee structure (0% maker promotion, standard taker):**
- Maker fee: **0%** (no volume requirement, applies to limit orders that add liquidity)
- Taker fee: **0.05%** (applies to market orders and limit orders that take liquidity)

Source: MEXC exchange documentation (https://www.mexc.com/fee)
Verified structurally: exchangeInfo API confirms pairs are spot-enabled. The API
does not return fee data in its public endpoint (makerCommission/takerCommission
are absent from the response), which is consistent with MEXC's documented 0% maker
being a promotional rate managed outside the standard fee field.

**Round-trip cost:**
- Complete RT (both sides as maker): 0% + 0% = **0% total**
- Forced close (maker entry + taker exit): 0% + 0.05% = **0.05%**

The edge hypothesis is most directly testable here: with 0% maker fees, the ONLY
cost is adverse selection. If price reverts after we provide liquidity, we capture
the spread for free. If it doesn't revert (informed flow), we lose on inventory.

---

## Task 2: Data Access Assessment

### What MEXC's Public API Provides (verified)

**Klines endpoint:** `GET /api/v3/klines?symbol=X&interval=60m&limit=500`
- Returns up to 500 1h OHLCV bars
- Historical depth: ~20 calendar days (2026-07-25 to present)
- Data fields: [open_time_ms, open, high, low, close, vol_base, close_time_ms, vol_quote]
- Pagination: startTime/endTime parameters available but API caps total at ~500 bars

**Trade-level data:**
- `GET /api/v3/trades?symbol=X&limit=1000`: returns the most recent ~200 trades (< 2h window for these pairs)
- No public historical trades endpoint (historicalTrades requires API key)

**Conclusion:** 1h OHLCV for 20 days is the complete public data available from MEXC
for these pairs without an API key. This is the data we use.

### Methodological Implications of Using OHLCV vs Ticks

| Property | Tick-level (prior thread) | 1h OHLCV (this thread) |
|---|---|---|
| Fill detection | Trade crosses our limit | Bar's H/L touches our limit |
| Fill timing precision | Exact (millisecond) | Within-bar (±30min) |
| Fill rate overestimation | High (ignores queue) | Moderate (ignores queue + all activity within bar) |
| AS measurement horizon | t+1min, t+5min, t+30min | t+1h, t+2h, t+4h, t+8h |
| Sample period | 30 days (prior) | 20 days (this) |

The OHLCV simulation is less precise but operates on TRUE MEXC data. The fill rate
haircut (50%) compensates for OHLCV over-detection.

---

## Task 3: Strategy Design

### Core Logic

```
For each 1h bar i (starting at bar 1):
    mid = close[i-1]                          # prior bar close as mid estimate
    bid = mid × (1 - spread/2)                # where we post bid
    ask = mid × (1 + spread/2)               # where we post ask

    BID FILL if low[i] ≤ bid and no pending bid position
        → record fill at price=bid, timestamp=bar_i_open
        → fill-conditional forward returns: close[i+1], close[i+2], close[i+4], ...

    ASK FILL if high[i] ≥ ask and no pending ask position
        → record fill at price=ask, timestamp=bar_i_open

    COMPLETE ROUND TRIP if pending bid and pending ask both exist
        → gross P&L = spread_pct (full spread captured, 0 maker fee)
        → both positions cleared

    FORCED CLOSE if pending position older than max_hold_bars
        → exit at close[i] using taker fee (0.05%)
        → net P&L = (close[i] - fill_price)/fill_price × direction - 0.0005
```

### Fill-Conditional Forward Return (Primary Diagnostic)

For every maker fill, record the price at each forward horizon.
Sign convention (same as prior thread):
- BID fill (we bought): AS = (px_future - fill_price) / fill_price  [negative if price fell]
- ASK fill (we sold): AS = -(px_future - fill_price) / fill_price  [negative if price rose]

If mean AS is positive: price reverts (we buy cheap, price recovers → profit).
If mean AS is negative: price continues against us (informed flow → loss).

### Fill Rate Assumption

Simulation counts a fill whenever the bar's H/L touches our limit. This OVERESTIMATES
true fills because:
1. Our order sits in a queue behind other limit orders at the same price
2. Small amounts of volume at our level may not fully fill us
3. We may have repriced before the touch (not modeled)

Conservative haircut: apply 50% to simulated fill count for all P&L calculations.
This is more aggressive than the prior thread's 60% because OHLCV-based detection
has more overshoot.

---

## Task 4: Pre-Registered Gate

See GATE.md (registered before backtest run). Summary:

| Criterion | Threshold | Gate |
|---|---|---|
| Fill count | ≥ 5 fills (20-day window) | G1 |
| Mean net per complete RT | > 0.10% | G2 |
| Fill-adj net monthly | > 0 at 50% fill rate | G3 |
| AS score at t+1h | > -0.15 × spread | G4 |
| AS score at t+4h | > -0.30 × spread | G5 |
| Sharpe (per-RT returns) | ≥ 0.3 | G6 |

**Pass rule:** All 6 criteria on BOTH pairs. Single-pair pass = data mining; no proceed.

---

## Honest Limitations

1. **20-day window is short.** Results are preliminary. Any pass is a green light for
   a 30-day paper trade, not live capital allocation.
2. **OHLCV fill detection overestimates fills.** The 50% haircut is a rough correction.
   True fill rates on thin books depend on our queue position (unknowable without L2 data).
3. **Hourly AS horizons differ from the paper.** Bianchi et al. measure reversals at
   30-minute to 2-hour horizons. Our t+1h and t+2h AS checks align with this range.
4. **MEXC microstructure may differ from Kraken.** MEXC likely has more bot-driven flow.
   Prior Kraken results may not replicate.
5. **No order book data.** We cannot estimate true spread or queue depth.

---

## Next Steps After Backtest

If BOTH pairs pass all 6 gates:
→ 30-day paper trade on MEXC (using API) before any capital allocation
→ Order book data (Crypto Lake or MEXC L2 stream) to validate fill rate assumption

If 0 or 1 pair passes:
→ Log outcome in KILL_LOG.md, close thread
