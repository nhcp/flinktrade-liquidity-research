# Handoff Record — ETHW/USDT

## Status: EVALUATED, REJECTED — not a live pair

Kept for the record because it was evaluated through the same process as the
live pairs and rejected on a well-characterized, repo-verified basis, not
because it is trading. It has **no live-trade start date and no independent
decision clock** — those fields don't apply to a rejected candidate, and this
doc should not be read as implying otherwise.

## Source run

Independent `liquidity_provision_v2` deep-validation thread (KILL_LOG.md
handoff on that thread, referred to there as "on Kelenva", not authored in
this repo) relayed ETHW/USDT as a fifth candidate, under the same battery used
for MINA, SFP, and XYO.

## Gate metrics from the relayed handoff

- Negative-control margins: 87% pass vs random-entry's 80%, vs shuffled-price's
  47% — a 40-point margin
- Fill-rate sweep: never below 70% majority-pass across the realistic range
- Fee-robust through 5bps
- No full-information adverse-selection failure
- Strong toxic-flow recovery

## This repo's own reconciliation — where it actually failed

Re-ran `data_fetch.py` → `simulator.py` → `analytics.py` against fresh MEXC 1h
klines (2026-07-31 to 2026-08-20, 20.8 days) at this repo's flat 1.0% spread /
$50 notional convention — the same process that passed SFP and XYO:

| Criterion | Threshold | Result |
|---|---|---|
| G1: Total fills | ≥ 5 | 215 ✓ |
| G2: Net/complete RT | > 0.10% | +1.0000% ✓ |
| G3: Fill-adj monthly | > 0 | **-14.0339% FAIL** ✗ |
| G4: AS at t+1h | > -0.15% | -0.0519% PASS ✓ |
| G5: AS at t+4h | > -0.30% | -0.0364% PASS ✓ |
| G6: Sharpe | ≥ 0.3 | 2.382 ✓ |
| DQ: Forced-close rate | ≤ 95% | 30.8% ✓ |
| **OVERALL** | **All 6** | **5/6 — FAIL (G3)** |

**Root cause:** forced-close severity, not fill-rate sensitivity or spread
choice. Mean net/forced-close = -0.71%, 2.3–3.4x worse than every other pair
in the pool at the time (MINA -0.28%, KAVA -0.21%, SFP -0.30%, XYO -0.21%). A
spread sweep confirmed this isn't a 1.0%-specific artifact: G3 only clears at a
non-primary 0.8% spread and fails again at 1.5%. Consistent with ETHW
(EthereumPoW) being materially more volatile intrabar (mean H-L range 0.875%
over the window) than the other pairs — the fixed 3-hour forced-close window
catches bigger adverse swings than this strategy's hold-time assumption
tolerates.

## Dates

- **Evaluated:** 2026-08-20
- **Added to live paper trade:** never — rejected same day
- **Independent decision date:** n/a

## Watch items

Not applicable — rejected before onboarding, so there is no live position to
monitor. The forced-close-severity finding is the disqualifying result itself,
not a post-onboarding watch item.

## References

GATE.md "Results — ETHW/USDT Evaluated (NOT added)"; PAPER_TRADE.md "Status
Update — 2026-08-20: ETHWUSDT evaluated, NOT added"; commit `d49665f`.
