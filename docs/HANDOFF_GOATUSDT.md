# Handoff Record — GOAT/USDT

## Status: LIVE (added to paper trade 2026-08-21)

## Source run

Relayed as the outcome of an external "wave 5" volume-band screen and
deep-validation thread — **not authored in this repo, and unlike the SFP/XYO/
ETHW handoffs, no artifact of this thread exists anywhere in this repo, this
host's filesystem, or its shell history** (no `mexc_client.py`, no wave 4/5
pool-count record, no 14-pair diff, no `KILL_LOG.md` entry for GOAT or
ANIMEUSDT). This is a materially weaker evidentiary starting point than SFP,
XYO, or ETHW had, and is called out explicitly rather than silently treated
the same way.

## Pool-size sanity check (performed before trusting anything downstream)

The relayed claim: wave 5 found 898 USDT pairs in the 30k-90k 24h-quoteVolume
band, up from wave 4's 244 (>3.5x in ~24h) — large enough to warrant checking
for a data-lag or query bug before trusting the "14 genuinely new pairs"
framing built on top of it.

Re-verification done here: queried MEXC's public `/api/v3/ticker/24hr`
endpoint live on 2026-08-21 (this repo's own MEXC-client conventions —
`urllib.request` + `urlencode` query building — since the original
`mexc_client.py` is not available to this repo), filtered to USDT-quoted
symbols with 24h quoteVolume in [30000, 90000).

**Result: 945 pairs currently in-band** — consistent with (in fact slightly
above) wave 5's reported 898, not a reversion toward wave 4's ~244.

**Verdict: STABLE.** Treated as a real, still-current market condition (broad
volume spike / listing wave across MEXC spot), not a transient bug or
data-lag artifact. This does not itself validate GOAT — it only clears wave
5's pool-level framing as trustworthy context rather than noise.

## Gate metrics that justified adding it

**Relayed deep-validation battery (external thread, unverifiable from this
repo):** 93% pass vs 77%/37% on its two negative controls, fee-robust. No
further detail (fill-rate sweep shape, toxic-flow recovery counts) was
available to reproduce here the way it was for SFP/XYO/ETHW's more detailed
relayed writeups.

**This repo's own reconciliation (registered, fully reproducible, GATE.md
"Results — GOAT/USDT Added"):** ran `data_fetch.py` → `simulator.py` →
`analytics.py` against fresh MEXC 1h klines (2026-08-01 to 2026-08-21, 20.8
days) at this repo's actual flat 1.0% spread / $50 notional convention — same
process used for SFP, XYO, ETHW:

| Criterion | Threshold | Result |
|---|---|---|
| G1: Total fills | ≥ 5 | 311 ✓ |
| G2: Net/complete RT | > 0.10% | +1.0000% ✓ |
| G3: Fill-adj monthly | > 0 | +63.9324% ✓ |
| G4: AS at t+1h | > -0.15% | +0.0206% PASS ✓ |
| G5: AS at t+4h | > -0.30% | +0.0189% PASS ✓ |
| G6: Sharpe | ≥ 0.3 | 13.349 ✓ |
| DQ: Forced-close rate | ≤ 95% | 14.2% ✓ |
| **OVERALL** | **All 6** | **6/6 PASS** |

This clean, independently-verifiable in-repo pass — not the unverifiable
relayed percentages — is the actual basis for adding GOAT live.

## Dates

- **Added to live paper trade:** 2026-08-21 (seed bar 2026-08-21T18:00:00Z,
  first trading bar 2026-08-21T19:00:00Z)
- **Independent decision date:** 2026-09-20 (30 days from 2026-08-21)

## Watch items noted at onboarding

1. **Forced-close severity.** Mean net/forced-close = -0.5043% at
   registration — already past the -0.30% "Stop level" guardrail
   PAPER_TRADE.md's weekly-monitoring table uses, and worse than every
   currently-active pair (MINA -0.28%, KAVA -0.21%, SFP -0.30%, XYO -0.21%),
   though clearly better than the rejected ETHW's -0.71%. G3 still clears
   because GOAT's forced-close rate is low (14.2% of fill events, in line
   with XYO's 14.7%), so complete-RT gains dominate the monthly figure — but
   this is the same metric whose severity sank ETHW, so it is flagged rather
   than waved through.
2. **Ask-fill AS asymmetry.** Bid-fill AS@1h = +0.1012% (n=156), ask-fill
   AS@1h = -0.0609% (n=154) — the ask side is mildly negative, a pattern not
   seen in XYO (both sides positive) or SFP (both sides near-zero). Well
   inside the G4 bound and far from the -0.50% disqualifying threshold, but
   new enough to watch in early weekly checks.
3. **Unverifiable source handoff.** Not a metric flag, but a standing
   evidentiary caveat: this repo's own 30-day paper trade carries more of the
   weight of proof for GOAT than it did for SFP or XYO, since the external
   deep-validation claim behind it cannot be checked here.

## References

GATE.md "Results — GOAT/USDT Added"; PAPER_TRADE.md "Status Update —
2026-08-21: GOATUSDT added" and "GOAT-specific monitoring"; commit — see this
task's onboarding commit.
