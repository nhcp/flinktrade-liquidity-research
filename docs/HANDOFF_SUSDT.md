# Handoff Record — S/USDT

## Status: LIVE (added to paper trade 2026-08-21)

## Source run

Relayed as the outcome of an external "widescreen" deep-validation screen/thread
— **not authored in this repo, and like GOAT's wave 5 relay, no artifact of this
thread exists anywhere in this repo, this host's filesystem, or its shell
history** (no pool-count record, no `KILL_LOG.md` entry for S, no
negative-control or fee-sensitivity percentages available to reproduce here).
The same relay also covered KAVAUSDT (already known to this repo, already
suspended — not re-evaluated) and flagged CSPRUSDT and NILUSDT as tension
cases, both verdicted KILL there — those two are excluded from this
onboarding and from the flinktrade.com dashboard update that follows it.

Note on symbol: the MEXC ticker for this pair is `SUSDT` (base asset `S`) —
not to be confused with `SFPUSDT`, an already-active, unrelated pair in this
same paper trade.

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
| G1: Total fills | ≥ 5 | 248 ✓ |
| G2: Net/complete RT | > 0.10% | +1.0000% ✓ |
| G3: Fill-adj monthly | > 0 | +14.9011% ✓ |
| G4: AS at t+1h | > -0.15% | -0.0864% PASS ✓ |
| G5: AS at t+4h | > -0.30% | -0.1146% PASS ✓ |
| G6: Sharpe | ≥ 0.3 | 5.312 ✓ |
| DQ: Forced-close rate | ≤ 95% | 22.3% ✓ |
| **OVERALL** | **All 6** | **6/6 PASS** |

Bid-fill AS@1h = +0.0292% (n=117), ask-fill AS@1h = -0.1905% (n=130) — a
pronounced ask-side negative asymmetry, larger than GOAT's (-0.0609%) or any
other active pair, though the blended G4 figure (-0.0864%) still passes with
headroom against the -0.15% threshold.

This clean, independently-verifiable in-repo pass — not the relayed claim —
is the actual basis for adding S live. It is, however, the least comfortable
pass of the three pairs added in this batch (see Watch items below).

## Fee-sensitivity result

Not separately swept for this batch (unlike ETHW's rejected evaluation, which
required a spread sweep to diagnose its G3 fail). S's G3 margin
(+14.9011%/month) is the thinnest of the three pairs added in this batch —
notably thinner than PIPPIN's (+51.4581%) despite PIPPIN's worse
per-forced-close severity, because S's forced-close rate (22.3%) is the
highest of the three. A fee or spread sensitivity sweep is a reasonable
follow-up if either the forced-close rate or severity worsens during weekly
monitoring — flagged here as a suggestion, not performed as part of this
onboarding.

## Toxic-flow / negative-control result

No independently reproducible negative-control or toxic-flow-recovery data
was available for this pair from the external relay (see Source run above).

## Dates

- **Added to live paper trade:** 2026-08-21 (seed bar 2026-08-21T21:00:00Z,
  first trading bar 2026-08-21T22:00:00Z, `start_date_utc`
  2026-08-21T22:12:00Z)
- **Independent decision date:** 2026-09-20 (30 days from 2026-08-21)

## Watch items noted at onboarding

1. **Ask-fill AS asymmetry.** Ask-fill AS@1h = -0.1905% (n=130) vs. bid-fill
   AS@1h = +0.0292% (n=117) — the largest ask-side negative asymmetry of any
   currently active pair (vs. GOAT's -0.0609%, XYO's and SFP's near-symmetric
   or positive profiles). Still comfortably inside the -0.15% G4 bound on the
   blended figure and far from the -0.50% disqualifying threshold, but the
   most pronounced directional pattern seen in this pool to date — worth
   close attention in early weekly checks.
2. **Forced-close severity.** Mean net/forced-close = **-0.6850%**, past the
   -0.30% "Stop level" guardrail and the second-worst in the pool after
   PIPPIN's -1.1084% (MINA -0.28%, KAVA -0.21%, SFP -0.30%, XYO -0.21%, GOAT
   -0.5043%, ETHW -0.71% rejected). G3 still clears (+14.9011%) because
   complete RTs (96) still outnumber forced closes (55), but this is the
   thinnest G3 margin of any pair added in this batch.
3. **Standing evidentiary caveat**, same as GOAT: this repo's own 30-day
   paper trade carries more of the weight of proof for S than for SFP or XYO,
   since the external widescreen deep-validation claim behind it cannot be
   checked here.

## References

GATE.md "Results — XPRUSDT / PIPPINUSDT / SUSDT Evaluated"; PAPER_TRADE.md
"Status Update — 2026-08-21: XPRUSDT, PIPPINUSDT, SUSDT added" and
"S-specific monitoring"; commit — see this task's onboarding commit.
