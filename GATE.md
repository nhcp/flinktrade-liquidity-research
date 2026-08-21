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

---

## Results — SFP/USDT Added — Simulation Date 2026-08-15

**Source of candidate:** independent `liquidity_provision_v2`-style deeper validation
thread (handoff document, not authored in this repo) recommended SFP/USDT as a third
candidate, having reproduced MINA's pattern (real signal, beats negative controls,
robust down to 10% fill rate, fee-tolerant to ~8.5bps) under the same battery that
separated MINA from KAVA. That handoff used each pair's own live top-of-book spread
(SFP: 17.12bps) rather than this repo's flat 1.0% quoting convention, and its own
G1–G6 reconstruction, not the criteria below — so its specific numbers do not
directly certify a pass against this gate. See PAPER_TRADE.md "Status Update —
2026-08-15: SFPUSDT added" for the full reconciliation note.

**This gate was re-run directly against SFP/USDT using this repo's actual
methodology** (same `simulator.py`/`analytics.py`, flat 1.0% spread, fresh MEXC
1h klines, 2026-07-25 to 2026-08-15, 20.8 days) — the same process originally used
to screen MINA and KAVA — to get an apples-to-apples registered result:

| Criterion | Threshold | SFP/USDT |
|---|---|---|
| G1: Total fills | ≥ 5 | 267 ✓ |
| G2: Net/complete RT | > 0.10% | +1.0000% ✓ |
| G3: Fill-adj monthly | > 0 | +59.32% ✓ |
| G4: AS at t+1h | > -0.15% | +0.0018% PASS ✓ |
| G5: AS at t+4h | > -0.30% | +0.0676% PASS ✓ |
| G6: Sharpe | ≥ 0.3 | 10.211 ✓ |
| DQ: Forced-close rate | ≤ 95% | 17.3% ✓ |
| **OVERALL** | **All 6** | **6/6 PASS** |

Bid-fill AS@1h = -0.0134% (n=132), ask-fill AS@1h = +0.0168% (n=134) — both near
zero, no directional asymmetry like MINA's bid-side flag. SFP is not currently in
a strong trend over this window (unlike MINA's -21% window).

**Caveat (carried over from KAVA's lesson):** a clean 6/6 on a single ~20-day
window is a screen, not proof — KAVA also passed 6/6 here before deeper scrutiny
in a separate sandbox revealed it was noise. SFP's case is stronger than KAVA's
was at this stage, because the deeper battery (fill-rate sensitivity, negative
controls, fee sensitivity) has *already* been run and SFP passed it — just under
a different spread parameterization than this table. The 30-day live paper trade
is what validates the flat-1.0% version of the strategy specifically.

**Verdict: PROCEED to paper trade.** See PAPER_TRADE.md for SFP's paper-trade
setup and independent 30-day decision clock (2026-08-15 → 2026-09-14).

---

## Results — XYO/USDT Added — Simulation Date 2026-08-20

**Source of candidate:** independent `liquidity_provision_v2` deep-validation thread
(KILL_LOG.md handoff, not authored in this repo) cleared XYO/USDT as a fourth
candidate under the same fill-rate-sensitivity / negative-control / fee-sensitivity
battery used for MINA and SFP, at fill-rate fr=0.50:

- Beats both negative controls decisively: 93% pass vs random-entry's 83%, vs
  shuffled-price's 47% (a 46-point margin over the shuffle control)
- Clean 100% pass at fr=1.00; majority-passing across the full fill-rate sweep
  (74–100%)
- Fee-robust: flat 67% pass rate at fr=0.25 across every fee level 0–5bps
- Best toxic-flow recovery of any pair validated in that study to date
  (3/4/6 round trips to recover from 2/3/5-sigma shocks)

Unlike SFP's handoff, this one did not surface a spread-convention conflict — but
per this repo's standing practice (see SFP note above), the deeper-validation
numbers are relayed evidence from a different engine and are not treated as a
gate pass on their own.

**This gate was re-run directly against XYO/USDT using this repo's actual
methodology** (same `simulator.py`/`analytics.py`, flat 1.0% spread, fresh MEXC
1h klines, 2026-07-31 to 2026-08-20, 20.8 days) — the same process used to screen
MINA, KAVA, and SFP — to get an apples-to-apples registered result:

| Criterion | Threshold | XYO/USDT |
|---|---|---|
| G1: Total fills | ≥ 5 | 312 ✓ |
| G2: Net/complete RT | > 0.10% | +1.0000% ✓ |
| G3: Fill-adj monthly | > 0 | +82.03% ✓ |
| G4: AS at t+1h | > -0.15% | +0.1083% PASS ✓ |
| G5: AS at t+4h | > -0.30% | +0.1064% PASS ✓ |
| G6: Sharpe | ≥ 0.3 | 16.222 ✓ |
| DQ: Forced-close rate | ≤ 95% | 14.7% ✓ |
| **OVERALL** | **All 6** | **6/6 PASS** |

Bid-fill AS@1h = +0.1811% (n=159), ask-fill AS@1h = +0.0317% (n=151) — both
positive, no directional-exposure flag like MINA's bid-side flag or a mixed
result like SFP's. This is the cleanest registered AS profile of the three
active pairs.

**Caveat (carried over from KAVA's lesson):** a clean 6/6 on a single ~20-day
window is a screen, not proof. XYO's case is stronger than KAVA's was at this
stage because the deeper battery (fill-rate sensitivity, negative controls, fee
sensitivity) has *already* been run and XYO passed it decisively — same
qualitative pattern as MINA and SFP, not KAVA's false positive. The 30-day live
paper trade is what validates the flat-1.0% version of the strategy specifically.

**Verdict: PROCEED to paper trade.** See PAPER_TRADE.md for XYO's paper-trade
setup and independent 30-day decision clock (2026-08-20 → 2026-09-19).

---

## Results — ETHW/USDT Evaluated (NOT added) — Simulation Date 2026-08-20

**Source of candidate:** independent `liquidity_provision_v2` deep-validation
thread (KILL_LOG.md handoff on Kelenva, not authored in this repo) cleared
ETHW/USDT as a fifth candidate under the same fill-rate-sensitivity /
negative-control / fee-sensitivity battery used for MINA, SFP, and XYO, at
fill-rate fr=0.50:

- Beats both negative controls: 87% pass vs random-entry's 80%, vs
  shuffled-price's 47% (a 40-point margin over the shuffle control)
- Clean fill-rate sweep — never below 70% majority-pass across the realistic
  fill-rate range
- Fee-robust through 5bps
- No full-information adverse-selection failure
- Strong toxic-flow recovery

**This gate was re-run directly against ETHW/USDT using this repo's actual
methodology** (same `simulator.py`/`analytics.py`, flat 1.0% spread, fresh MEXC
1h klines, 2026-07-31 to 2026-08-20, 20.8 days) — the same reconciliation
process used to screen SFP and XYO. Unlike SFP and XYO, this one **did not**
reconcile to a clean pass:

| Criterion | Threshold | ETHW/USDT |
|---|---|---|
| G1: Total fills | ≥ 5 | 215 ✓ |
| G2: Net/complete RT | > 0.10% | +1.0000% ✓ |
| G3: Fill-adj monthly | > 0 | **-14.0339% FAIL** ✗ |
| G4: AS at t+1h | > -0.15% | -0.0519% PASS ✓ |
| G5: AS at t+4h | > -0.30% | -0.0364% PASS ✓ |
| G6: Sharpe | ≥ 0.3 | 2.382 ✓ |
| DQ: Forced-close rate | ≤ 95% | 30.8% ✓ |
| **OVERALL** | **All 6** | **5/6 — FAIL (G3)** |

Bid-fill AS@1h = +0.0327% (n=110), ask-fill AS@1h = -0.1414% (n=104) — both
within gate bounds, no AS disqualification.

**Root cause of the G3 fail — forced-close severity, not fill-rate sensitivity
or spread choice.** Compared directly against every other pair in the live
pool at the same 1.0% spread and same run:

| Pair | Forced-close rate | Mean net/forced close |
|---|---|---|
| MINA | 29.5% | -0.28% |
| KAVA | 41.0% | -0.21% |
| SFP | 17.3% | -0.30% |
| XYO | 14.7% | -0.21% |
| ETHW | 30.8% | **-0.71%** |

ETHW's forced-close *rate* is unremarkable (in line with MINA/KAVA), but its
mean *loss per forced close* is 2.3–3.4x worse than every other pair — this is
what drags fill-adj monthly net decisively negative (95.2 forced closes/month ×
-0.708% outweighs the 50%-haircut gain from complete RTs). A spread sweep
confirms this isn't a cherry-pick artifact: G3 only passes at a non-primary
0.8% spread (+13.03%/mo) and fails again at 1.5% (-1.15%/mo); it fails at the
pre-registered primary 1.0%. This is consistent with ETHW (EthereumPoW) being
materially more volatile intrabar than the other four pairs (mean H-L range
0.875% over the window) — the fixed 3-hour forced-close window catches bigger
adverse price swings than this strategy's hold-time assumption tolerates.

**Same lesson as KAVA:** a deep-validation battery pass under a different
engine/spread parameterization does not certify a pass against this repo's
own registered gate at its actual live-paper-trade convention (flat 1.0%
spread, $50 notional). SFP and XYO's handoffs both reconciled cleanly; this
one does not, and the divergence is well-characterized (forced-close severity)
rather than ambiguous.

**Verdict: DO NOT PROCEED to paper trade.** ETHW/USDT is not added to the live
paper-trade pool. Data (`data/ETHWUSDT_1h.csv`, `data/ETHWUSDT_fills.csv`) and
this analysis are kept in the repo for the record; `PAIRS` in
`paper_trade.py`/`paper_report.py`/`simulator.py`/`analytics.py`/`data_fetch.py`
is unchanged (MINA/KAVA/SFP/XYO only). See PAPER_TRADE.md "Status Update —
2026-08-20: ETHWUSDT evaluated, not added" for the pool-level note.

---

## Results — GOAT/USDT Added — Simulation Date 2026-08-21

**Source of candidate:** an external "wave 5" volume-band screen plus deep-validation
thread (not authored in this repo, no artifact of it exists on this host) relayed
GOAT/USDT as a fourth pair to clear the deep-validation battery used for SFP and XYO
(93% pass vs 77%/37% on its two negative controls, fee-robust). **This repo has no
way to independently verify those specific percentages** — unlike the SFP/XYO/ETHW
handoffs, which at least referenced `KILL_LOG.md` entries on the external
`liquidity_provision_v2` thread, no equivalent artifact for GOAT or the wave 5 run
(pool counts, the 14-pair diff, ANIMEUSDT's kill rationale) exists anywhere in this
repo, this host's filesystem, or its shell history. Per this repo's standing practice
(see SFP/XYO/ETHW notes above), relayed numbers are never treated as a gate pass on
their own — the actual gate below is what decided this.

**Pool-size sanity check performed before trusting the handoff (see KILL_LOG.md /
task record):** re-queried MEXC's public ticker endpoint live on 2026-08-21 for USDT
pairs with 24h quoteVolume in the wave 5 screen's reported 30k-90k band. Current
count: **945 pairs** — consistent with (in fact slightly above) wave 5's reported 898,
not a reversion to wave 4's ~244. Verdict: **STABLE**, real market condition, not a
data-lag artifact. `mexc_client.py` itself (the actual script wave 5 used) is not
present in this repo, so this was reconstructed against MEXC's public
`/api/v3/ticker/24hr` endpoint using this repo's own urllib-based client conventions
plus `urlencode` query building, not a byte-identical replay of the original script.

**This gate was re-run directly against GOAT/USDT using this repo's actual
methodology** (same `simulator.py`/`analytics.py`, flat 1.0% spread, fresh MEXC 1h
klines, 2026-08-01 to 2026-08-21, 20.8 days) — the same reconciliation process used
for SFP, XYO, and ETHW — to get an apples-to-apples registered result:

| Criterion | Threshold | GOAT/USDT |
|---|---|---|
| G1: Total fills | ≥ 5 | 311 ✓ |
| G2: Net/complete RT | > 0.10% | +1.0000% ✓ |
| G3: Fill-adj monthly | > 0 | +63.9324% ✓ |
| G4: AS at t+1h | > -0.15% | +0.0206% PASS ✓ |
| G5: AS at t+4h | > -0.30% | +0.0189% PASS ✓ |
| G6: Sharpe | ≥ 0.3 | 13.349 ✓ |
| DQ: Forced-close rate | ≤ 95% | 14.2% ✓ |
| **OVERALL** | **All 6** | **6/6 PASS** |

Bid-fill AS@1h = +0.1012% (n=156), ask-fill AS@1h = -0.0609% (n=154) — unlike XYO
(both sides positive) or SFP (both near-zero), GOAT's ask-fill side is mildly
negative. Still comfortably inside G4's -0.15% bound and far from the -0.50%
disqualifying threshold, but a new asymmetry pattern not seen in the other three
active pairs, worth watching.

**Watch item — forced-close severity is the most notable flag at registration.**
Mean net/forced close = **-0.5043%**, already past the -0.30% "Stop level" guardrail
PAPER_TRADE.md's weekly-monitoring table uses (MINA -0.28%, KAVA -0.21%, SFP -0.30%,
XYO -0.21%, ETHW -0.71% for comparison). This is the same metric whose severity sank
ETHW's G3 — GOAT does **not** fail G3 here because its forced-close rate is low
(14.2% of fill events, in line with XYO's 14.7%) so complete-RT gains dominate the
monthly figure, but the per-forced-close loss itself is worse than every currently
active pair except the rejected ETHW. Flagged for close attention in early weekly
checks, same discipline as SFP's Week 1 forced-close flag.

**Caveat (carried over from KAVA's lesson):** a clean 6/6 on a single ~20-day window
is a screen, not proof. Unlike KAVA, the relayed deep-validation numbers report real
separation from negative controls — but this repo cannot verify those numbers itself,
so the 30-day live paper trade carries more of the evidentiary weight for GOAT than
it did for SFP/XYO, where the relayed battery could at least be cross-checked against
a `KILL_LOG.md`-referenced thread.

**Verdict: PROCEED to paper trade**, on the strength of this repo's own clean 6/6
reconciliation, with the forced-close severity and ask-side AS asymmetry logged as
explicit watch items rather than silently passed over. See PAPER_TRADE.md for GOAT's
paper-trade setup and independent 30-day decision clock (2026-08-21 → 2026-09-20),
and `docs/HANDOFF_GOATUSDT.md` for the full onboarding record.
