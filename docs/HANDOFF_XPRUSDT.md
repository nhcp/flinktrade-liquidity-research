# Handoff Record — XPR/USDT

## Status: LIVE (added to paper trade 2026-08-21)

## Source run

Relayed as the outcome of an external "widescreen" deep-validation screen/thread
— **not authored in this repo, and like GOAT's wave 5 relay, no artifact of this
thread exists anywhere in this repo, this host's filesystem, or its shell
history** (no pool-count record, no `KILL_LOG.md` entry for XPR, no
negative-control or fee-sensitivity percentages available to reproduce here).
The same relay also covered KAVAUSDT (already known to this repo, already
suspended — not re-evaluated) and flagged CSPRUSDT and NILUSDT as tension
cases, both verdicted KILL there — those two are excluded from this
onboarding and from the flinktrade.com dashboard update that follows it.

## Gate metrics that justified adding it

**Relayed deep-validation battery (external thread, unverifiable from this
repo):** no specific percentages or artifact were available to this task
beyond the pair being relayed as clearing the widescreen screen. Per this
repo's standing practice, this was not treated as a gate pass on its own.

**This repo's own reconciliation (registered, fully reproducible, GATE.md
"Results — XPRUSDT / PIPPINUSDT / SUSDT Evaluated"):** ran `data_fetch.py` →
`simulator.py` → `analytics.py` against fresh MEXC 1h klines (2026-08-01 to
2026-08-21, 20.8 days) at this repo's actual flat 1.0% spread / $50 notional
convention — same process used for SFP, XYO, ETHW, GOAT:

| Criterion | Threshold | Result |
|---|---|---|
| G1: Total fills | ≥ 5 | 249 ✓ |
| G2: Net/complete RT | > 0.10% | +1.0000% ✓ |
| G3: Fill-adj monthly | > 0 | +79.0895% ✓ |
| G4: AS at t+1h | > -0.15% | +0.2683% PASS ✓ |
| G5: AS at t+4h | > -0.30% | +0.3079% PASS ✓ |
| G6: Sharpe | ≥ 0.3 | 15.787 ✓ |
| DQ: Forced-close rate | ≤ 95% | 19.4% ✓ |
| **OVERALL** | **All 6** | **6/6 PASS** |

Bid-fill AS@1h = +0.4039% (n=132), ask-fill AS@1h = +0.1139% (n=116) — both
sides positive, no directional-exposure or asymmetry flag. Mean
net/forced-close = **+0.1003%**, positive and better than every other active
pair (MINA -0.28%, KAVA -0.21%, SFP -0.30%, XYO -0.21%, GOAT -0.5043%, and
the rejected ETHW's -0.71%). This is the cleanest reconciliation of the three
pairs added in this batch, closest in shape to XYO's.

This clean, independently-verifiable in-repo pass — not the relayed claim —
is the actual basis for adding XPR live.

## Fee-sensitivity result

Not separately swept for this batch (unlike ETHW's rejected evaluation, which
required a spread sweep to diagnose its G3 fail). No indication of
fee-fragility at the registered 1.0% spread; the G3 margin (+79.0895%/month)
is the largest of the three pairs added in this batch and would need a very
large adverse shift to flip negative.

## Toxic-flow / negative-control result

No independently reproducible negative-control or toxic-flow-recovery data
was available for this pair from the external relay (see Source run above).
This repo's own AS profile (both sides positive at t+1h) is the closest
available proxy for "no toxic flow dominance," and it is clean.

## Dates

- **Added to live paper trade:** 2026-08-21 (seed bar 2026-08-21T21:00:00Z,
  first trading bar 2026-08-21T22:00:00Z, `start_date_utc`
  2026-08-21T22:12:00Z)
- **Independent decision date:** 2026-09-20 (30 days from 2026-08-21)

## Watch items noted at onboarding

None noted. XPR's registered reconciliation is clean on every metric checked
at registration — positive AS on both sides, positive mean net/forced-close,
the largest G3 margin of the three pairs added in this batch, and a
forced-close rate (19.4%) well inside the DQ bound.

## References

GATE.md "Results — XPRUSDT / PIPPINUSDT / SUSDT Evaluated"; PAPER_TRADE.md
"Status Update — 2026-08-21: XPRUSDT, PIPPINUSDT, SUSDT added" and
"XPR-specific monitoring"; commit — see this task's onboarding commit.
