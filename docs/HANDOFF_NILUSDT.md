# Handoff Record — NIL/USDT

## Status: LIVE (added to paper trade 2026-08-23)

## This is a verdict reversal

NIL/USDT was **originally KILLed** by the same external "widescreen"
deep-validation relay that produced the XPR/PIPPIN/S batch (see
`docs/HANDOFF_XPRUSDT.md`, GATE.md "Results — XPRUSDT / PIPPINUSDT / SUSDT
Evaluated"). That relay flagged NIL (alongside CSPRUSDT) as a "tension case"
and verdicted it **KILL** — excluded from `PAIRS` and the dashboard at that
time, same as CSPR.

Reported separately (outside this repo, not independently reproducible here)
as the reason for the original KILL: the result was a **1-seed-of-30
statistical fluke** — it failed on one Monte-Carlo seed out of thirty
sampled, not a majority of seeds. A retest at higher seed counts
(n=50/100/200/300) reportedly reconfirmed a real **PASS at a 12–19.5pp
margin, stable across all four larger samples**.

**Neither the original KILL nor the retest PASS is treated as authoritative
here.** As with every prior relay in this repo (SFP/XYO/ETHW/GOAT/XPR/PIPPIN/
S), no seed-level artifact for either claim — pool counts, per-seed pass/fail,
the specific fluke seed, the retest's own numbers — exists anywhere in this
repo, this host's filesystem, or its shell history (checked by search before
writing this doc). **The only basis for reversing NIL's verdict and adding it
to live paper trade is this repo's own independent gate re-run below**, run
fresh for this task, following the identical practice used for every other
pair.

## Gate metrics that justified reversing the verdict

**This repo's own reconciliation (registered, fully reproducible, GATE.md
"Results — NILUSDT (verdict reversal)"):** ran `data_fetch.py` →
`simulator.py` → `analytics.py` against fresh MEXC 1h klines (2026-08-02 to
2026-08-23, 20.8 days) at this repo's actual flat 1.0% spread / $50 notional
convention — same process used for every pair before it, global constants
only, no per-pair tuning:

| Criterion | Threshold | Result |
|---|---|---|
| G1: Total fills | ≥ 5 | 567 ✓ |
| G2: Net/complete RT | > 0.10% | +1.0000% ✓ |
| G3: Fill-adj monthly | > 0 | +112.4609% ✓ |
| G4: AS at t+1h | > -0.15% | -0.1394% PASS ✓ |
| G5: AS at t+4h | > -0.30% | -0.1650% PASS ✓ |
| G6: Sharpe | ≥ 0.3 | 10.931 ✓ |
| DQ: Forced-close rate | ≤ 95% | 2.5% ✓ |
| **OVERALL** | **All 6** | **6/6 PASS** |

This is a genuine independent PASS on this repo's own methodology — not the
relayed retest claim taken at face value. But it is also the **least
comfortable pass registered in this repo to date**, carrying three watch
items louder than anything seen for any prior pair:

1. **G4 margin is the thinnest on record.** -0.1394% clears the -0.15%
   threshold by only 0.0106pp. Every other pair's blended G4 margin has
   cleared with more room (MINA -0.0202%, KAVA +0.0546%, SFP +0.0018%, XYO
   +0.1083%, GOAT +0.0206%, XPR +0.2683%, PIPPIN -0.0831%, S -0.0864%).
2. **Ask-fill AS@1h (-0.2752%, n=284) would fail G4 outright if gated in
   isolation.** Bid-fill AS@1h is flat-to-clean (-0.0032%, n=283); it is the
   bid side pulling the blended mean inside the -0.15% bound. This is the
   same kind of bid/ask split MINA's original registration flagged as a
   borderline note (bid-only -0.1564%) — here the asymmetric side is ask,
   and the magnitude is larger.
3. **Forced-close severity is the worst in the pool by ~4x.** Mean
   net/forced-close = **-4.2899%**, versus the next-worst pair (PIPPIN,
   -1.1084%) and every other pair (MINA -0.28%, KAVA -0.21%, SFP -0.30%, XYO
   -0.21%, GOAT -0.5043%, XPR +0.1003%, S -0.6850%; even ETHW's rejected
   -0.71% is well inside this). G3 still clears decisively — in fact the
   largest monthly margin of any pair to date (+112.4609%) — only because
   NIL's forced-close *rate* is the lowest in the pool (2.5% of fill events,
   14 forced closes vs. 276 complete RTs out of 567 total fills). This is
   the same rate-dilutes-severity mechanism that let GOAT's and PIPPIN's G3
   clear despite elevated forced-close losses, but the raw severity here is
   far outside anything seen before.

None of these trip a disqualifying condition: AS@t+1h stays well clear of the
-0.50%×spread DQ bound (even the ask-only -0.2752% is), and the 2.5%
forced-close rate is nowhere near the 95% DQ bound.

This clean, independently-verifiable in-repo pass — not the relayed retest
claim — is the actual basis for reversing NIL's verdict and adding it live.

## Fee-sensitivity result

Not separately swept for this task (consistent with how XPR/PIPPIN/S were
handled — a sweep was only re-run for ETHW, whose primary-spread G3 failed).
G3's margin (+112.4609%/month) is the largest of any pair registered in this
repo, so it is not fee-fragile at the registered 1.0% spread on its own — but
given how thin the G4 margin and how severe the forced-close loss are, a
sweep would be reasonable next-step diligence if NIL's live numbers start
drifting.

## Toxic-flow / negative-control result

No independently reproducible negative-control or toxic-flow-recovery data
was available from the external relay for either the original KILL or the
retest (see "This is a verdict reversal" above). This repo's own AS profile
is the closest available proxy, and it is a genuine but marginal pass: the
blended mean clears G4/G5, but the ask-side asymmetry (-0.2752% at t+1h) is a
real toxic-flow signal on that side specifically, not fully clean the way
XPR's or XYO's profiles were.

## Dates

- **Added to live paper trade:** 2026-08-23 (seed bar 2026-08-23T11:00:00Z,
  first trading bar 2026-08-23T12:00:00Z, `start_date_utc`
  2026-08-23T12:13:55Z)
- **Independent decision date:** 2026-09-22 (30 days from 2026-08-23)

## Watch items noted at onboarding

Three, all more severe than any prior pair's watch items — see "Gate metrics
that justified reversing the verdict" above:
1. G4 margin only 0.0106pp above threshold (thinnest on record).
2. Ask-fill AS@1h (-0.2752%) would fail G4 in isolation.
3. Mean net/forced-close (-4.2899%) worst in the pool by ~4x, offset only by
   the lowest forced-close rate in the pool (2.5%).

NIL should be prioritized first in weekly monitoring among all active pairs
— see PAPER_TRADE.md "NIL-specific monitoring."

## References

GATE.md "Results — NILUSDT (verdict reversal)"; PAPER_TRADE.md "Status Update
— 2026-08-23: NILUSDT added (verdict reversal)" and "NIL-specific
monitoring"; original KILL referenced in GATE.md "Results — XPRUSDT /
PIPPINUSDT / SUSDT Evaluated" and PAPER_TRADE.md "Status Update — 2026-08-21:
XPRUSDT, PIPPINUSDT, SUSDT added"; commit — see this task's onboarding
commit.
