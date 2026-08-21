# Handoff Record — XYO/USDT

## Status: LIVE (added to paper trade)

## Source run

Independent `liquidity_provision_v2` deep-validation thread (KILL_LOG.md handoff
on that thread, not authored in this repo) cleared XYO/USDT as the fourth
candidate for this project, under the same fill-rate-sensitivity /
negative-control / fee-sensitivity battery used to separate MINA (real signal)
from KAVA (noise) and to add SFP.

## Gate metrics that justified adding it

**Relayed deep-validation battery (external thread, fr=0.50 unless noted):**
- Negative-control margins: 93% pass vs random-entry's 83%, vs shuffled-price's
  47% — a 46-point margin over the shuffle control
- Fill-rate sweep: clean 100% pass at fr=1.00; majority-passing across the full
  sweep (74–100%)
- Fee-sensitivity: flat 67% pass rate at fr=0.25 across every fee level 0–5bps
- Toxic-flow recovery: best of any pair validated in that study to date
  (3/4/6 round trips to recover from 2/3/5-sigma shocks)

These numbers were computed on a different engine than this repo's, so per
standing practice they were not treated as a gate pass on their own.

**This repo's own reconciliation (registered, verifiable, GATE.md "Results —
XYO/USDT Added"):** re-ran `data_fetch.py` → `simulator.py` → `analytics.py`
against fresh MEXC 1h klines (2026-07-31 to 2026-08-20, 20.8 days) at this
repo's actual flat 1.0% spread / $50 notional convention:

| Criterion | Threshold | Result |
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
positive, the cleanest AS profile of the pairs active at the time (no
directional-exposure flag like MINA's bid-side flag, no mixed result like
SFP's).

## Dates

- **Added to live paper trade:** 2026-08-20 (seed bar 2026-08-20T19:00:00Z,
  first trading bar 2026-08-20T20:00:00Z)
- **Independent decision date:** 2026-09-19 (30 days from 2026-08-20)

## Watch items noted at onboarding

None noted at onboarding. XYO registered the cleanest AS profile of the active
pool at the time — no bid/ask asymmetry flag, no elevated forced-close-loss
flag, no spread-convention reconciliation conflict (unlike SFP's, which used a
narrower live-spread convention externally).

## References

GATE.md "Results — XYO/USDT Added"; PAPER_TRADE.md "Status Update — 2026-08-20:
XYOUSDT added" and "XYO-specific monitoring"; commit `579fa27`.
