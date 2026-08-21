# Handoff Record — PIPPIN/USDT

## Status: LIVE (added to paper trade 2026-08-21)

## Source run

Relayed as the outcome of an external "widescreen" deep-validation screen/thread
— **not authored in this repo, and like GOAT's wave 5 relay, no artifact of this
thread exists anywhere in this repo, this host's filesystem, or its shell
history** (no pool-count record, no `KILL_LOG.md` entry for PIPPIN, no
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
| G1: Total fills | ≥ 5 | 361 ✓ |
| G2: Net/complete RT | > 0.10% | +1.0000% ✓ |
| G3: Fill-adj monthly | > 0 | +51.4581% ✓ |
| G4: AS at t+1h | > -0.15% | -0.0831% PASS ✓ |
| G5: AS at t+4h | > -0.30% | -0.0403% PASS ✓ |
| G6: Sharpe | ≥ 0.3 | 9.116 ✓ |
| DQ: Forced-close rate | ≤ 95% | 11.1% ✓ |
| **OVERALL** | **All 6** | **6/6 PASS** |

Bid-fill AS@1h = -0.0959% (n=178), ask-fill AS@1h = -0.0707% (n=183) — both
mildly negative but comfortably inside G4's -0.15% bound and far from the
-0.50% disqualifying threshold, no material asymmetry between sides.

This clean, independently-verifiable in-repo pass — not the relayed claim —
is the actual basis for adding PIPPIN live.

## Fee-sensitivity result

Not separately swept for this batch (unlike ETHW's rejected evaluation, which
required a spread sweep to diagnose its G3 fail). Given PIPPIN's already
elevated forced-close severity (see watch item below), a fee or spread
sensitivity sweep is a reasonable follow-up if the forced-close guardrail
trips during weekly monitoring — flagged here as a suggestion, not performed
as part of this onboarding.

## Toxic-flow / negative-control result

No independently reproducible negative-control or toxic-flow-recovery data
was available for this pair from the external relay (see Source run above).

## Dates

- **Added to live paper trade:** 2026-08-21 (seed bar 2026-08-21T21:00:00Z,
  first trading bar 2026-08-21T22:00:00Z, `start_date_utc`
  2026-08-21T22:12:00Z)
- **Independent decision date:** 2026-09-20 (30 days from 2026-08-21)

## Watch items noted at onboarding

1. **Forced-close severity — the most notable flag of any pair currently in
   the pool, including the rejected ETHW.** Mean net/forced-close =
   **-1.1084%**, versus MINA -0.28%, KAVA -0.21%, SFP -0.30%, XYO -0.21%,
   GOAT -0.5043%, and ETHW's rejected -0.71%. G3 still clears decisively
   (+51.4581%/month) only because PIPPIN's forced-close rate is low (11.1% of
   fill events, in line with XYO's/GOAT's low range) and its complete-RT
   volume is high (160 complete RTs, 230.9/month) — the same mechanism that
   kept GOAT's G3 positive despite an elevated forced-close loss, but here
   the per-event loss itself is worse than the pair (ETHW) whose G3 actually
   failed on this exact metric. This is flagged for close weekly-check
   attention, not treated as disqualifying today, since the registered gate
   criterion (G3, fill-adjusted monthly net) is what the gate actually
   measures and it passes with a wide margin.
2. **Standing evidentiary caveat**, same as GOAT: this repo's own 30-day
   paper trade carries more of the weight of proof for PIPPIN than for SFP or
   XYO, since the external widescreen deep-validation claim behind it cannot
   be checked here.

## References

GATE.md "Results — XPRUSDT / PIPPINUSDT / SUSDT Evaluated"; PAPER_TRADE.md
"Status Update — 2026-08-21: XPRUSDT, PIPPINUSDT, SUSDT added" and
"PIPPIN-specific monitoring"; commit — see this task's onboarding commit.
