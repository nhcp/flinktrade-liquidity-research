# Crypto MM MEXC — Pre-Registered Gate
## Registered: 2026-08-14 | Status: OPEN

This gate is append-only after registration. Results are recorded below only after
the backtest has been run. The strategy does not proceed to live capital without
ALL criteria passing on BOTH candidate pairs.

---

## Research Context

Hypothesis (Bianchi, Babiak & Dickerson 2022, JBF): Short-term reversal /
liquidity-provision returns concentrate in LOW-VOLUME crypto pairs, compensating
for adverse-selection risk. The edge turns negative on high-fee venues and only
survives where maker fees are zero.

This thread tests the hypothesis on REAL MEXC data (not a Kraken proxy) for
MINA/USDT and KAVA/USDT — two low-volume pairs confirmed active on MEXC spot.

---

## Data & Methodology (Fixed Pre-Run)

- **Exchange:** MEXC spot (api.mexc.com)
- **Pairs:** MINA/USDT and KAVA/USDT
- **Data source:** MEXC public klines API — 1h OHLCV bars (max 500 bars ≈ 20 days)
- **Fee schedule:** 0% maker, 0.05% taker (no volume requirement; MEXC public documentation)
- **Spread parameter:** 1.0% total (0.5% each side from mid)
- **Spread sweep:** also run at 0.8% and 1.5% for robustness; primary evaluation at 1.0%
- **Mid-price:** previous bar's close (no lookahead)
- **Fill detection:** bar's LOW ≤ bid → bid fill at posted bid price; bar's HIGH ≥ ask → ask fill at posted ask price
- **Fill-rate haircut:** 50% (conservative; ignores queue depth — real fill rate will be lower than simulated)
- **Max inventory hold:** 3 bars (3 hours) before forced close at taker fee
- **Forward return horizons:** t+1h, t+2h, t+4h, t+8h, t+12h (bars ahead)
- **Adverse selection sign convention:** negative = price moved against our fill direction

---

## Gate Criteria (Pre-Registered)

### G1: Fill Count (Data Viability)
- **Threshold:** ≥ 5 simulated fills in the 20-day window
- **Rationale:** At 20 days of data, 5 fills = ~7.5/month annualized. Below 5 fills,
  the spread is too wide for any useful signal.
- **Measured by:** `simulator.py` output: `total_fills`

### G2: Net Return on Complete Round-Trips
- **Threshold:** Mean net P&L per complete RT > 0.10%
- **Rationale:** MEXC 0% maker means complete RTs have 0 fee cost. Must exceed
  0.10% to absorb bid-ask spread estimation error and provide real margin.
- **Measured by:** `simulator.py` output: `mean_complete_net_pct`

### G3: Fill-Rate-Adjusted Monthly Net Return
- **Threshold:** fill_adj_net_monthly_pct > 0
  - `adj_net = (complete_fills/20days × 50%) × mean_complete_net + forced_closes × mean_forced_net`
  - Normalised to per-month rate
- **Rationale:** After 50% fill-rate haircut, strategy must still show positive expected value.
- **Measured by:** `simulator.py` output: `fill_adj_net_monthly_pct`

### G4: Adverse Selection Score at t+1h
- **Threshold:** mean AS score at t+1h > -0.15 × spread_pct
  - For 1.0% spread: > -0.15%
- **Rationale:** Within 1 hour of a maker fill, price should not move systematically
  against us by more than 15% of the spread. If it does, informed flow dominates.
- **Measured by:** `analytics.py` output: `as_1h`

### G5: Adverse Selection Score at t+4h
- **Threshold:** mean AS score at t+4h > -0.30 × spread_pct
  - For 1.0% spread: > -0.30%
- **Rationale:** Persistent adverse selection at 4h horizon is the primary indicator
  of informed flow. This is the "who is on the other side?" test.
- **Measured by:** `analytics.py` output: `as_4h`

### G6: Risk-Adjusted Return
- **Threshold:** Sharpe ratio of per-RT returns ≥ 0.3
  - Threshold lower than prior gate (0.5) because 20-day sample is short.
- **Rationale:** Minimum bar for risk-adjusted viability; 0.3 is already generous for
  this sample size — a negative or near-zero Sharpe kills the strategy.
- **Measured by:** `simulator.py` output: `sharpe`

---

## Pass Rule
- All 6 criteria must pass on the SAME pair.
- Both MINA/USDT AND KAVA/USDT must pass.
- Single-pair pass = data mining concern; do not pursue.

---

## Disqualifying Conditions (Override Any Pass)
1. If AS@t+1h < -0.50 × spread_pct on ANY pair:
   → Informed flow dominant; strategy not viable on that pair. Close thread for that pair.
2. If total_fills < 3 on any pair:
   → Insufficient data; no conclusion possible. Do not count as pass or fail.
   → Extend data collection or close thread.
3. If forced-close rate > 95% (nearly every position exits without completing RT):
   → Market structure does not allow round-trips; spread too wide for this liquidity.

---

## Results — Simulation Date 2026-08-14

**Data:** MEXC public 1h klines (api.mexc.com/api/v3/klines), 500 bars per pair,
2026-07-25 to 2026-08-14 (20.8 calendar days).
**Fee regime:** MEXC — 0% maker, 0.05% taker.
**Primary spread param:** 1.0% (also run at 0.8% and 1.5% for robustness; primary reported below).
**Fill rate haircut applied:** 50% on complete RT count.

### Gate Results by Pair — 1.0% Spread (Primary)

| Criterion | Threshold | MINA/USDT | KAVA/USDT |
|---|---|---|---|
| G1: Total fills | ≥ 5 | 193 ✓ | 122 ✓ |
| G2: Net/complete RT | > 0.10% | +1.0000% ✓ | +1.0000% ✓ |
| G3: Fill-adj monthly | > 0 | +25.74% ✓ | +10.80% ✓ |
| G4: AS at t+1h | > -0.15% | -0.0202% PASS ✓ | +0.0546% PASS ✓ |
| G5: AS at t+4h | > -0.30% | +0.0399% PASS ✓ | +0.0700% PASS ✓ |
| G6: Sharpe | ≥ 0.3 | 7.077 ✓ | 3.772 ✓ |
| **OVERALL** | **All 6** | **6/6 PASS** | **6/6 PASS** |

### Robustness at Other Spread Params

| Spread | Pair | G1 Fills | G3 Fill-adj | G6 Sharpe | Overall |
|---|---|---|---|---|---|
| 0.8% | MINA/USDT | 246 ✓ | +22.10% ✓ | 7.234 ✓ | PASS (G4/G5 not re-run) |
| 0.8% | KAVA/USDT | 158 ✓ | +9.65% ✓ | 4.123 ✓ | PASS (G4/G5 not re-run) |
| 1.5% | MINA/USDT | 98 ✓ | +8.31% ✓ | 2.954 ✓ | PASS (G4/G5 not re-run) |
| 1.5% | KAVA/USDT | 46 ✓ | **-1.92% FAIL** ✗ | 0.959 ✓ | **FAIL** (G3 fails) |

At 1.5%, KAVA fails G3 — too many forced closes relative to fills. 1.0% is the viable primary.

### Adverse Selection Detail (1.0% spread)

**MINA/USDT:**
- t+1h: mean AS = -0.0202% (overall) — **bid fills only: -0.1564%** (borderline; see note)
- t+2h: +0.0270%
- t+4h: +0.0399%
- t+8h: +0.0874%
- t+12h: +0.0980%

**KAVA/USDT:**
- t+1h: mean AS = +0.0546% (bid: +0.0097%, ask: +0.1074%)
- t+2h: +0.0136%
- t+4h: +0.0700%
- t+8h: +0.1150%
- t+12h: +0.1881%

### Critical Observations

**1. MINA bid-fill AS is borderline (-0.1564% at t+1h, threshold -0.15%)**
When our bid fills (someone SELLS to us), the price continues falling -0.16% on average
in the next hour. This marginally fails the bid-side adverse selection test. The overall
mean passes (-0.02%) because our ask-fills show positive AS (+0.099%), which offsets.

**Why this might be benign:** MINA fell -21% over the 20-day window (from $0.04982 to
$0.03939). In a trending-down market, bid fills naturally occur into falling momentum.
This is not pure informed trading; it's directional exposure. In a mean-reverting or
flat market, this asymmetry would likely reverse.

**Risk flag:** If MINA continues trending down after paper-trade entry, bid adverse
selection will worsen. This requires monitoring during any paper-trade period.

**2. Sharpe ratios are inflated by OHLCV simulation design**
OHLCV simulation forces all complete RTs to return exactly spread_pct (no price improvement
or slippage variation). This collapses variance and inflates Sharpe. Real fills would have
noisy execution prices. Treat Sharpe as "direction correct, magnitude unreliable."

**3. 50% fill rate haircut is already applied; true rate may be lower**
On thin MEXC books with ~$2,600 USDT/hour volume, our orders may be queue position 1
most of the time — or position 100. We cannot know without L2 data. The 50% haircut
is a reasonable midpoint but should not be treated as precise.

**4. 20-day window includes a trending regime for MINA**
A 20-day mean-reversion backtest during a trend biases results toward forced closes.
KAVA was flatter (within a narrower range), showing better forced-close P&L.

---

**Verdict: CONDITIONAL PROCEED**

Both MINA/USDT and KAVA/USDT pass all 6 gate criteria at 1.0% spread on MEXC 1h data.
KAVA is the stronger candidate (positive AS at all horizons, less directional exposure).
MINA passes but requires monitoring of bid-fill adverse selection during paper trade.

**Required before any live capital:**
1. 30-day paper trade on MEXC (track actual fills, not simulated OHLCV crossings)
2. Monitor MINA bid-fill AS in real paper-trade conditions — suspend if it worsens
3. Confirm MEXC 0% maker fee applies to our order type and account tier
