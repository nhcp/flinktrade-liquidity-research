# Crypto MM MEXC — 30-Day Paper Trade
## MINA/KAVA started: 2026-08-14 | Target end: 2026-09-13
## SFP started: 2026-08-15 | Target end: 2026-09-14 (independent clock — see Status Update below)
## XYO started: 2026-08-20 | Target end: 2026-09-19 (independent clock — see Status Update below)
## GOAT started: 2026-08-21 | Target end: 2026-09-20 (independent clock — see Status Update below)
## XPR/PIPPIN/S started: 2026-08-21 | Target end: 2026-09-20 (independent clocks — see Status Update below)
## NIL started: 2026-08-23 | Target end: 2026-09-22 (independent clock, verdict reversal — see Status Update below)

**Purpose:** Validate MINA/USDT and KAVA/USDT backtest results against real
MEXC kline data before any capital allocation. Both pairs passed the 6/6
gate on 20 days of MEXC 1h data. This paper trade is the required final step.

---

## Status Update — 2026-08-15: KAVA/USDT SUSPENDED

**KAVA/USDT was suspended on 2026-08-15**, ahead of hitting its own
adverse-selection stop condition, based on new evidence from the
`liquidity_provision_v2` strengthening-research thread (see
`liquidity_provision_v2/docs/FINAL_REPORT.md`) showing the original 6/6 gate
pass was a false positive from having tested only 2 pairs:

- **Gate fails under a perfect fill assumption:** KAVA fails its own gate in
  the majority of seeds even at a 100% fill rate — the original pass was
  never really about fill-rate assumptions being conservative.
- **No signal vs. negative control:** KAVA's result vs. a shuffled/randomized-price
  control is statistically indistinguishable from noise (60% vs. 43% pass
  rate).
- **Fee-fragile:** KAVA flips net-negative at just a 5bps fee change.

By contrast, MINA/USDT clearly beats its shuffled-price control (97% vs.
23% pass rate) and remains majority-passing down to ~15% fill rate — real
signal. **MINA/USDT continues running untouched.**

This paper trade is now effectively MINA-only. KAVA's row below is kept for
the historical record; disregard the "KAVA is the stronger candidate" note
under MINA-specific monitoring — it predates this finding and is superseded.

---

## Status Update — 2026-08-15: SFPUSDT added

**SFP/USDT joined this paper trade on 2026-08-15**, on the recommendation of an
independent deeper-validation handoff (not authored in this repo) that ran the
same fill-rate-sensitivity / negative-control / fee-sensitivity battery that
originally separated MINA (real signal) from KAVA (noise) — and found SFP
reproduces MINA's pattern: majority-passing down to 10% fill rate, clearly
beats both a random-entry control (80% vs 63%) and a shuffled-price control
(80% vs 50%), and stays majority-passing even at the top of the modeled fee
range (breakeven fee 8.56bps vs. KAVA's 5bps flip).

**Important reconciliation flag from the handoff, resolved below:** that study
did not use this repo's flat 1.0% quoting spread — it used each pair's own live
top-of-book spread (SFP: 17.12bps at snapshot time), and found that a literal
flat 1.0% spread collapsed to ~0% gate pass rate for MINA, KAVA, *and* SFP alike
in its own (different) simulation engine. Since MINA and KAVA are real,
currently-running paper trades at flat 1.0% in *this* repo, that result could
not be taken at face value here.

**Resolution:** re-ran this repo's actual `data_fetch.py` → `simulator.py` →
`analytics.py` pipeline against fresh real SFPUSDT MEXC data at the same flat
1.0% spread used for MINA/KAVA (the literal existing infra, unchanged). Result:
**6/6 gate pass**, 267 fills over 20.8 days, near-zero AS in both directions
(bid -0.013%, ask +0.017% at t+1h — cleaner than MINA's -0.156% bid-side flag).
See GATE.md "Results — SFP/USDT Added" for the full table. This means the flat
1.0% convention works fine for SFP in this repo's real methodology; the collapse
reported by the handoff was specific to its own (different, narrower-spread)
simulation engine and does not apply here. SFP is paper-traded below at the
same flat 1.0% spread as MINA, not at 17.12bps.

**Caveat carried forward:** the handoff's deeper robustness numbers (fill-rate
sensitivity, negative controls, fee sensitivity) were computed at SFP's own
17.12bps spread, not at this repo's 1.0%. The specific percentages don't
transfer, but the qualitative finding — SFP shows real signal vs. noise,
unlike KAVA — is a meaningful signal that this flat-1.0% registered gate run
independently corroborates.

**SFP runs on its own independent 30-day clock**, started 2026-08-15 (its own
first paper-trade run), decision date 2026-09-14 — tracked separately from
MINA's 2026-09-13 decision date since it joined a day later. `paper_trade.py`
and `paper_report.py` now track `start_date_utc` per pair for this reason.

---

## Status Update — 2026-08-20: XYOUSDT added

**XYO/USDT joined this paper trade on 2026-08-20**, on the recommendation of an
independent `liquidity_provision_v2` deep-validation thread (KILL_LOG.md handoff,
not authored in this repo) that ran the same fill-rate-sensitivity /
negative-control / fee-sensitivity battery used for MINA and SFP. At fr=0.50, XYO
beats both negative controls decisively (93% pass vs random-entry's 83%, vs
shuffled-price's 47% — a 46-point margin), is clean 100% pass at fr=1.00 and
majority-passing across the full fill-rate sweep (74–100%), is fee-robust (flat
67% pass rate at fr=0.25 across every fee level 0–5bps), and shows the best
toxic-flow recovery of any pair validated in that study so far (3/4/6 round trips
to recover from 2/3/5-sigma shocks).

**Reconciliation check (same discipline applied to SFP):** re-ran this repo's
actual `data_fetch.py` → `simulator.py` → `analytics.py` pipeline against fresh
real XYOUSDT MEXC data at the same flat 1.0% spread used for MINA/SFP (the
literal existing infra, unchanged) rather than trusting the handoff's numbers at
face value. Result: **6/6 gate pass**, 312 fills over 20.8 days, both bid and ask
AS positive at t+1h (bid +0.181%, ask +0.032%) — the cleanest AS profile of the
three active pairs, no directional flag at all. See GATE.md "Results — XYO/USDT
Added" for the full table. XYO is paper-traded below at the same flat 1.0%
spread and $50/fill notional as MINA and SFP — the repo shows no evidence of
per-pair tuning of either parameter (both are single global constants in
`paper_trade.py`/`paper_report.py`), so no reconciliation flag applies here.

**XYO runs on its own independent 30-day clock**, started 2026-08-20 (its own
first paper-trade run, seed bar 2026-08-20T19:00:00Z), decision date
**2026-09-19** — tracked separately from MINA's 2026-09-13 and SFP's 2026-09-14
decision dates. Adding XYO did not touch MINA's or SFP's `start_date_utc` or
live totals (verified via `--dry-run` and `--status` before and after).

---

## Status Update — 2026-08-20: ETHWUSDT evaluated, NOT added

**ETHW/USDT was evaluated as a fifth candidate on 2026-08-20**, on the same
recommendation basis as SFP and XYO — an independent `liquidity_provision_v2`
deep-validation thread (KILL_LOG.md handoff on Kelenva, not authored in this
repo) reporting it beats both negative controls at fr=0.50 (87% real vs 80%
random-entry vs 47% shuffled-price, a 40-point margin), a clean fill-rate
sweep (never below 70% majority-pass across the realistic range), fee
robustness through 5bps, no full-information adverse-selection failure, and
strong toxic-flow recovery.

**Applying the same reconciliation discipline used for SFP and XYO** (re-run
this repo's actual `data_fetch.py` → `simulator.py` → `analytics.py` pipeline
against fresh real ETHWUSDT MEXC data at the flat 1.0% spread and $50 notional,
rather than trusting the handoff's numbers — which were computed on a
different engine/spread — at face value), the result did **not** reconcile
cleanly: **5/6 gate pass, G3 (fill-adj monthly net) FAILS at -14.03%/month**,
driven by forced-close losses averaging -0.71% per forced close — 2.3–3.4x
worse than every other pair currently in the pool (MINA -0.28%, KAVA -0.21%,
SFP -0.30%, XYO -0.21%). A spread sweep confirmed this isn't a 1.0%-specific
artifact to dismiss: G3 only clears at a non-primary 0.8% spread and fails
again at 1.5%. Full detail, including the root-cause forced-close comparison,
in GATE.md "Results — ETHW/USDT Evaluated (NOT added)".

**This is the same failure mode that suspended KAVA**: a deep-validation
battery pass under a different engine/spread parameterization does not
transfer to this repo's own registered gate at its actual live-paper-trade
convention. Unlike SFP and XYO, whose reconciliation runs confirmed the
handoff's qualitative finding, ETHW's reconciliation contradicts it — this
repo's own methodology finds real, well-characterized negative EV from
forced closes, plausibly explained by ETHW (EthereumPoW) being materially
more volatile intrabar than the other four pairs.

**Decision: ETHW/USDT is NOT added to this paper trade.** No change to
`PAIRS` in any script, no new entry in `paper_trade_state.json`, and MINA's
(2026-09-13), SFP's (2026-09-14), and XYO's (2026-09-19) clocks and live
totals are untouched. `data/ETHWUSDT_1h.csv` and `data/ETHWUSDT_fills.csv`
are kept in the repo for reproducibility of this analysis, not as live
paper-trade inputs.

Full onboarding-evaluation record (rejected — not a live pair):
`docs/HANDOFF_ETHWUSDT.md`.

---

## Status Update — 2026-08-21: GOATUSDT added

**GOAT/USDT joined this paper trade on 2026-08-21**, relayed via an external
"wave 5" volume-band screen and deep-validation thread — not authored in this
repo, and unlike the SFP/XYO/ETHW handoffs, **no artifact of that thread (wave
counts, the 14-pair diff, `mexc_client.py`, or a `KILL_LOG.md` entry) exists
anywhere in this repo or host.** The relayed claim is that GOAT beats both
negative controls decisively (93% pass vs 77%/37%) and is fee-robust. This repo
cannot independently verify those specific percentages and does not treat them
as a gate pass on their own, per standing practice.

**Pool-size sanity check (done first, before trusting the handoff at all):**
the wave 5 screen reported 898 USDT pairs in the 30k-90k 24h-quoteVolume band,
up >3.5x from wave 4's 244 pairs in roughly 24 hours — large enough to warrant
checking for a data-lag or query bug before trusting anything downstream of it.
Re-querying MEXC's public ticker endpoint live on 2026-08-21 found **945** USDT
pairs currently in that band — consistent with (slightly above) wave 5's count,
not a reversion to wave 4's ~244. **Verdict: STABLE** — a real, currently-still-
elevated market condition (broad volume spike / listing wave), not a transient
bug. GOAT's own gate result below does not depend on this pool-size figure
either way; the check was to decide whether wave 5's "14 genuinely new pairs"
framing was trustworthy context, not to validate GOAT itself.

**This gate was re-run directly against GOAT/USDT using this repo's actual
methodology** (same `data_fetch.py` → `simulator.py` → `analytics.py` pipeline,
flat 1.0% spread, fresh MEXC 1h klines, 2026-08-01 to 2026-08-21, 20.8 days) —
the same reconciliation process used for SFP, XYO, and ETHW. Result: **6/6 gate
pass**, 311 fills, positive AS at both t+1h (+0.0206%) and t+4h (+0.0189%). See
GATE.md "Results — GOAT/USDT Added" for the full table and two watch items
flagged at registration: mean net/forced-close of -0.5043% (already past the
-0.30% weekly-monitoring guardrail, though G3 still clears because the
forced-close rate is only 14.2%), and a mild negative ask-fill AS asymmetry
(-0.0609% at t+1h) not seen in XYO or SFP. Neither is disqualifying; both are
logged for early weekly-check attention.

GOAT is paper-traded at the same flat 1.0% spread and $50/fill notional as the
other four pairs — both remain single global constants in
`paper_trade.py`/`paper_report.py`, no per-pair tuning, so no reconciliation
flag applies here.

**GOAT runs on its own independent 30-day clock**, started 2026-08-21 (its own
first paper-trade run, seed bar 2026-08-21T18:00:00Z), decision date
**2026-09-20** — tracked separately from MINA's 2026-09-13, SFP's 2026-09-14,
and XYO's 2026-09-19 decision dates. Adding GOAT did not touch MINA's, SFP's,
or XYO's `start_date_utc` or live totals (verified via `--dry-run`/`--status`
before and after).

Full onboarding record, including the un-verifiable-handoff caveat above in one
place: `docs/HANDOFF_GOATUSDT.md`.

**ANIMEUSDT was also part of the wave 5 screen and was killed upstream** (fee-
sensitivity-cliff / toxic-flow rationale, recorded in the external thread's own
`KILL_LOG.md`, not this repo's). It is **not** a paper-trade candidate and is
correctly absent from `PAIRS` in every script in this repo — no action taken
here beyond confirming that absence.

---

## Status Update — 2026-08-21: XPRUSDT, PIPPINUSDT, SUSDT added

**XPR/USDT, PIPPIN/USDT, and S/USDT joined this paper trade on 2026-08-21**,
relayed via an external "widescreen" deep-validation screen/thread — not
authored in this repo. That same relay covered KAVAUSDT (already known here,
already suspended — not re-evaluated) and flagged CSPRUSDT and NILUSDT as
tension cases, both verdicted **KILL** by that external screen. CSPR and NIL
are **not** onboarded here and are **not** added anywhere in this repo or the
flinktrade.com dashboard — they stay excluded pending further review, per the
task that requested this batch. As with GOAT's wave-5 relay, no artifact of
this widescreen thread exists anywhere in this repo or host (checked by
search before writing this section), so the relayed claim was not treated as
a gate pass on its own for any of the three pairs.

**This repo's own reconciliation** (same `data_fetch.py` → `simulator.py` →
`analytics.py` pipeline, flat 1.0% spread, fresh MEXC 1h klines, 2026-08-01 to
2026-08-21, 20.8 days — same process used for SFP/XYO/ETHW/GOAT) is what
actually decided onboarding. All three independently reconciled to a clean
**6/6 gate pass**:

- **XPRUSDT:** 249 fills, both-sides-positive AS (+0.2683% @1h, +0.3079% @4h),
  positive mean net/forced-close (+0.1003%) — the cleanest of the three, no
  watch items.
- **PIPPINUSDT:** 361 fills, mildly negative but in-bounds AS (-0.0831% @1h,
  -0.0403% @4h). **Watch item:** mean net/forced-close of -1.1084% — worse
  than every other pair in the pool, including the rejected ETHW (-0.71%);
  G3 still clears because forced-close rate is low (11.1%) and complete-RT
  volume is high.
- **SUSDT:** 248 fills, in-bounds blended AS (-0.0864% @1h, -0.1146% @4h) but
  a pronounced ask-side asymmetry (-0.1905% @1h, largest of any active pair).
  **Watch items:** that asymmetry, plus mean net/forced-close of -0.6850%
  (second-worst in the pool) and the thinnest G3 margin of the three
  (+14.9011%).

Full detail in GATE.md "Results — XPRUSDT / PIPPINUSDT / SUSDT Evaluated".
All three are paper-traded at the same flat 1.0% spread and $50/fill notional
as every other pair — single global constants in `paper_trade.py` /
`paper_report.py`, no per-pair tuning.

**Each runs on its own independent 30-day clock**, all three started
2026-08-21 (seed bar 2026-08-21T21:00:00Z, first trading bar
2026-08-21T22:00:00Z, `start_date_utc` 2026-08-21T22:12:00Z), decision date
**2026-09-20** for all three — same calendar decision date as GOAT since they
joined the same day, but each tracked as its own independent clock in
`paper_trade_state.json`, not shared with GOAT's or any other pair's.
Verified via `--dry-run`/`--status` before and after that MINA's, SFP's,
XYO's, and GOAT's `start_date_utc` and live totals were untouched by the
addition.

Full onboarding records: `docs/HANDOFF_XPRUSDT.md`, `docs/HANDOFF_PIPPINUSDT.md`,
`docs/HANDOFF_SUSDT.md`.

---

## Status Update — 2026-08-23: NILUSDT added (verdict reversal)

**NILUSDT joined this paper trade on 2026-08-23**, reversing its own original
verdict. NIL was previously KILLed by the same external "widescreen" relay
covered above (2026-08-21 status update), alongside CSPRUSDT, both flagged as
"tension cases." Reported separately (outside this repo, unverifiable here)
as the reason: the original KILL was a **1-seed-of-30 statistical fluke**,
and a retest at higher seed counts (n=50/100/200/300) reportedly reconfirmed
a real PASS at a 12–19.5pp margin, stable across all four larger samples. As
with the original KILL, **no artifact of that retest exists anywhere in this
repo, this host's filesystem, or its shell history** — neither claim was
taken at face value, per this repo's standing practice for every relay above.

**This repo's own reconciliation** (same `data_fetch.py` → `simulator.py` →
`analytics.py` pipeline, flat 1.0% spread, fresh MEXC 1h klines, 2026-08-02
to 2026-08-23, 20.8 days) is what actually decided this reversal. NIL
independently reconciles to a **6/6 gate pass** — 567 fills, blended AS
in-bounds at both horizons (-0.1394% @1h, -0.1650% @4h), Sharpe 10.931 — but
with the three loudest watch items logged for any pair added to this repo:

1. **G4 margin is the thinnest on record** — clears the -0.15% threshold by
   only 0.0106pp.
2. **Ask-fill AS@1h (-0.2752%) would fail G4 in isolation** — the bid side
   (-0.0032%) is what pulls the blended mean inside bounds.
3. **Mean net/forced-close (-4.2899%) is the worst in the pool**, ~4x worse
   than the next-worst pair (PIPPIN, -1.1084%); G3 still clears decisively
   (+112.4609%/month, the largest margin of any pair to date) only because
   NIL's forced-close rate is the lowest in the pool (2.5%).

None of these trip a disqualifying condition. Full detail: GATE.md "Results —
NILUSDT (verdict reversal)".

CSPRUSDT is **not** part of this reversal — its own retest artifact, if one
exists, was not presented with this task, and it remains excluded pending a
separate independent re-gate.

NIL is paper-traded at the same flat 1.0% spread and $50/fill notional as
every other pair — single global constants in `paper_trade.py` /
`paper_report.py`, no per-pair tuning.

**NIL runs on its own independent 30-day clock**, started 2026-08-23 (its own
first paper-trade run, seed bar 2026-08-23T11:00:00Z, first trading bar
2026-08-23T12:00:00Z, `start_date_utc` 2026-08-23T12:13:55Z), decision date
**2026-09-22** — tracked separately from every other pair's decision date.
Adding NIL did not touch any other pair's `start_date_utc` or live totals
(verified via `--dry-run`/`--status` before and after).

Full onboarding record: `docs/HANDOFF_NILUSDT.md`.

---

## What This Is (and Is Not)

**What it is:** A live replay of the backtest strategy using MEXC's public
klines API. Each hour, the runner checks whether the current bar's H/L would
have triggered a fill, and records it identically to how the backtest did.

**What it is not:** Real order placement. No API key is used. No orders
go to the exchange. We are tracking what the strategy *would have done*
if we had been posting limit orders continuously since the start date.

**Why this methodology is valid:** The OHLCV-touch fill assumption is the
same assumption used in the backtest that generated the gate results. If
those results hold in the paper trade, we have confirmed the assumption is
reasonable for this market structure over an extended window.

---

## Parameters (Fixed — Same as Backtest Primary)

| Parameter         | Value    |
|---|---|
| Pairs             | MINA/USDT, KAVA/USDT, SFP/USDT, XYO/USDT, GOAT/USDT, XPR/USDT, PIPPIN/USDT, S/USDT |
| Spread            | 1.0% (0.5% each side from mid) — same flat convention for all pairs |
| Mid reference     | Previous 1h bar's close |
| Max hold          | 3 bars (3 hours) before forced close |
| Forced close fee  | 0.05% taker (MEXC) |
| Maker fee         | 0% (MEXC limit-order promotion) |
| Notional          | $50 USDT per fill (for dollar tracking; no real $ committed) |

---

## Running the Paper Trade

### Initial setup (run once)

```bash
cd /home/nhcp/research/crypto_mm_mexc
python src/paper_trade.py
```

On first run, this records the current kline bar as the "seed" bar and
exits. No trades are placed on the first run.

### Hourly runner

Run once per hour, any time after the top of the hour:

```bash
python src/paper_trade.py
```

The runner fetches the latest klines, identifies any completed bars since
the last run, and processes them in chronological order. Running it 2× in
the same hour is safe — the second run finds no new bars.

**Recommended: set up a cron job**

```cron
# Run at minute 5 every hour (bars close at top of hour; 5-min buffer)
5 * * * * cd /home/nhcp/research/crypto_mm_mexc && python src/paper_trade.py >> logs/paper_trade.log 2>&1
```

### View status

```bash
python src/paper_trade.py --status        # state only; no API calls
python src/paper_trade.py --dry-run       # what would happen; no writes
python src/paper_report.py                # full P&L + AS report
```

---

## Monitoring Schedule

### Weekly checks (every 7 days)

Run `python src/paper_report.py` and verify, for each active pair:

| Metric | Warning level | Stop level |
|---|---|---|
| Bid-fill AS at t+1h (any pair) | < -0.15% | < -0.50% (DQ) |
| Forced-close rate | > 80% | > 95% (gate DQ) |
| Mean net/forced close | < -0.10% | < -0.30% |

Log findings in the Results section below. Each pair is checked against its own
clock (MINA/KAVA weekly boundaries land on 2026-08-21/28, 2026-09-04; SFP's land
one day later: 2026-08-22/29, 2026-09-05; XYO's land 2026-08-27, 2026-09-03,
2026-09-10; GOAT's land 2026-08-28, 2026-09-04, 2026-09-11; XPR/PIPPIN/S's land
2026-08-28, 2026-09-04, 2026-09-11 — same as GOAT's since they share a start date,
but each pair's clock is independently tracked; NIL's land 2026-08-30, 2026-09-06,
2026-09-13).

### MINA-specific monitoring

MINA fell -21% during the 20-day backtest window (2026-07-25 to 2026-08-14).
The bid-fill AS at t+1h was -0.156% — borderline against the -0.15% gate.

**Stop condition:** If MINA bid-fill AS at t+1h drops below -0.50%, this
indicates genuine informed-flow dominance, not just directional exposure.
Suspend MINA immediately:

```bash
python src/paper_trade.py --suspend MINAUSDT
```

~~KAVA's bid-fill AS was +0.010% — well clear of the threshold. KAVA is the
stronger candidate; MINA needs the paper trade to resolve the ambiguity.~~
**Superseded 2026-08-15:** see "Status Update" above — KAVA's 6/6 gate pass
was a false positive (no signal vs. negative control, fee-fragile, fails
even at 100% fill). KAVA is suspended; MINA is the pair with real signal.

### SFP-specific monitoring

SFP's registered gate run (2026-08-15, see GATE.md) showed near-zero AS in
both directions — no directional-exposure flag like MINA's. Its deeper
validation (separate handoff, see Status Update above) found comfortable,
not marginal, adverse-selection headroom (13.7% of captured edge at +1h vs.
the 50% cutoff used in that study) and flagged that SFP's live spread moved
+33% between two snapshots taken ~2 hours apart — a reminder that spread on
this pair is not static, though this repo's own quoting is a fixed 1.0% and
does not depend on the live spread.

**Stop condition:** same as MINA — if SFP bid-fill AS at t+1h drops below
-0.50%, suspend immediately:

```bash
python src/paper_trade.py --suspend SFPUSDT
```

### XYO-specific monitoring

XYO's registered gate run (2026-08-20, see GATE.md) showed the cleanest AS
profile of any active pair — both bid and ask AS positive at t+1h (bid +0.181%,
ask +0.032%), no directional-exposure flag at all. Its deep-validation handoff
(separate `liquidity_provision_v2` thread, see Status Update above) found the
best toxic-flow recovery of any pair validated in that study (3/4/6 round trips
to recover from 2/3/5-sigma shocks), decisive separation from both negative
controls at fr=0.50 (46-point margin over the shuffled-price control), and
fee-robustness holding flat at fr=0.25 across the full 0–5bps fee range.

**Stop condition:** same as MINA/SFP — if XYO bid-fill AS at t+1h drops below
-0.50%, suspend immediately:

```bash
python src/paper_trade.py --suspend XYOUSDT
```

### GOAT-specific monitoring

GOAT's registered gate run (2026-08-21, see GATE.md) passed 6/6 with positive AS
at both t+1h and t+4h, but flagged two watch items at onboarding: mean
net/forced-close of -0.5043% (already past the -0.30% "Stop level" guardrail
below — the same metric whose severity sank ETHW's G3, though GOAT's low 14.2%
forced-close rate keeps G3 positive here) and a mild negative ask-fill AS
asymmetry (-0.0609% at t+1h, vs XYO's positive both sides and SFP's near-zero
both sides). See `docs/HANDOFF_GOATUSDT.md` for the full detail.

**Stop condition:** same as the other pairs — if GOAT bid-fill AS at t+1h drops
below -0.50%, suspend immediately:

```bash
python src/paper_trade.py --suspend GOATUSDT
```

Also watch the forced-close guardrail specifically for GOAT given its
already-elevated registered value: two consecutive weekly checks with mean
net/forced-close still below -0.30% should be treated as a live confirmation of
the registration-time flag, not a new surprise.

### XPR-specific monitoring

XPR's registered gate run (2026-08-21, see GATE.md) was the cleanest of the
three pairs added that day — both bid and ask AS positive at t+1h (bid
+0.4039%, ask +0.1139%), no directional-exposure flag, and a positive mean
net/forced-close (+0.1003%, better than every other active pair). No watch
items were noted at onboarding.

**Stop condition:** same as the other pairs — if XPR bid-fill AS at t+1h
drops below -0.50%, suspend immediately:

```bash
python src/paper_trade.py --suspend XPRUSDT
```

### PIPPIN-specific monitoring

PIPPIN's registered gate run (2026-08-21, see GATE.md) passed 6/6 but flagged
the most severe forced-close watch item of any active pair: mean
net/forced-close of **-1.1084%**, worse than every other pair in the pool
including the rejected ETHW's -0.71%. G3 clears only because forced-close
rate is low (11.1%) and complete-RT volume is high — the same mechanism that
kept GOAT's G3 positive, but at a more severe per-event loss than GOAT's.

**Stop condition:** same as the other pairs — if PIPPIN bid-fill AS at t+1h
drops below -0.50%, suspend immediately:

```bash
python src/paper_trade.py --suspend PIPPINUSDT
```

Given the severity of the registered forced-close flag, treat two consecutive
weekly checks with mean net/forced-close still below -0.30% (the standard
guardrail) as a live confirmation warranting closer review, not routine
noise — the registered value is already more than 3x that guardrail.

### S-specific monitoring

S's registered gate run (2026-08-21, see GATE.md) passed 6/6 with the
thinnest G3 margin of the three pairs added that day (+14.9011%) and two
watch items: a pronounced ask-side AS asymmetry (-0.1905% at t+1h, the
largest of any active pair, though the blended G4 figure of -0.0864% still
clears with headroom) and an elevated mean net/forced-close (-0.6850%,
second-worst in the pool after PIPPIN).

**Stop condition:** same as the other pairs — if S bid-fill AS at t+1h drops
below -0.50%, suspend immediately:

```bash
python src/paper_trade.py --suspend SUSDT
```

Because S's G3 margin is the thinnest of any pair added in this batch, weekly
checks should watch both the forced-close guardrail and any drop in
complete-RT volume — either alone eroding further could flip G3 negative
faster here than for XPR or PIPPIN.

### NIL-specific monitoring

NIL's registered gate run (2026-08-23, see GATE.md "Results — NILUSDT
(verdict reversal)") passed 6/6 but with the loudest watch items of any pair
onboarded here: a G4 margin of only 0.0106pp above the -0.15% threshold (the
thinnest on record), an ask-fill AS@1h of -0.2752% that would fail G4 on its
own if gated separately, and a mean net/forced-close of -4.2899% — the worst
in the pool by roughly 4x, kept from sinking G3 only because NIL's
forced-close rate (2.5%) is the lowest of any pair.

**Stop condition:** same as the other pairs — if NIL bid-fill or blended AS
at t+1h drops below -0.50%, suspend immediately:

```bash
python src/paper_trade.py --suspend NILUSDT
```

Because NIL's G4 margin is razor-thin and its forced-close severity is
unprecedented in this pool, weekly checks should prioritize NIL first among
active pairs: any further AS drift at t+1h risks a DQ-level breach faster
than for any other pair, and any rise in forced-close rate (even a small one,
given how severe each forced close is) could flip G3 negative quickly. This
pair should not be treated as a routine addition — it is being watched more
closely than any other pair in this file given the reversed verdict and the
severity of its watch items.

---

## Files

| File | Purpose |
|---|---|
| `data/paper_trade_state.json` | Persistent state: positions, last bar, totals |
| `data/paper_trade_events.csv` | Append-only event log: every fill and RT outcome |
| `src/paper_trade.py` | Hourly runner |
| `src/paper_report.py` | P&L and adverse-selection report |
| `docs/HANDOFF_<PAIR>.md` | Per-pair onboarding record: which run/handoff passed it, the gate metrics that justified adding it, date added, decision date, watch items at onboarding |

The events CSV is the canonical record. If the state JSON is ever lost or
corrupted, it can be reconstructed by replaying the events.

**Handoff docs on file:** `docs/HANDOFF_XYOUSDT.md`, `docs/HANDOFF_ETHWUSDT.md`
(evaluated, rejected — kept for the record, not a live pair), `docs/HANDOFF_GOATUSDT.md`,
`docs/HANDOFF_XPRUSDT.md`, `docs/HANDOFF_PIPPINUSDT.md`, and `docs/HANDOFF_SUSDT.md`.
MINA/KAVA predate the external-handoff pattern (they were this gate's original two
candidates, not sourced from a deep-validation thread) and SFP's watch items are
already documented inline above, so none of those three get a separate file.

---

## Decision Framework

Each pair is decided independently on its own clock — SFP joined a day after
MINA/KAVA and XYO joined 5 days after that; each is evaluated on its own 30-day
window, not forced to align with the others.

### MINA/KAVA decision — 2026-09-13 (30 days from 2026-08-14)

**Proceed to capital ($200 MINA, $50/fill) if:**
- [ ] MINA: AS at t+1h > -0.15% × spread  (G4 maintained)
- [ ] MINA: AS at t+4h > -0.30% × spread  (G5 maintained)
- [ ] MINA: bid-fill AS at t+1h did NOT drop below -0.50% at any point
- [ ] MINA: forced-close rate < 95%
- [ ] Total realized P&L across 30 days: positive (any positive)

**Kill if:** MINA bid-fill AS at t+1h < -0.50% at any weekly check, or
forced-close rate > 95% for 2 consecutive weeks.

KAVA is already suspended (2026-08-15, false-positive gate pass) and excluded
from this decision — see Status Update above.

### SFP decision — 2026-09-14 (30 days from 2026-08-15, its own clock)

**Proceed to capital ($200 SFP, $50/fill) if:**
- [ ] SFP: AS at t+1h > -0.15% × spread  (G4 maintained)
- [ ] SFP: AS at t+4h > -0.30% × spread  (G5 maintained)
- [ ] SFP: bid-fill AS at t+1h did NOT drop below -0.50% at any point
- [ ] SFP: forced-close rate < 95%
- [ ] Total realized P&L across 30 days: positive (any positive)

**Kill if:** SFP bid-fill AS at t+1h < -0.50% at any weekly check, or
forced-close rate > 95% for 2 consecutive weeks. (SFP has no negative-control
analog to KAVA's "loses to random entry" flag — its deeper validation cleared
that check — so no early-suspicion trigger beyond the standard AS/forced-close
stop conditions applies here yet.)

### XYO decision — 2026-09-19 (30 days from 2026-08-20, its own clock)

**Proceed to capital ($200 XYO, $50/fill) if:**
- [ ] XYO: AS at t+1h > -0.15% × spread  (G4 maintained)
- [ ] XYO: AS at t+4h > -0.30% × spread  (G5 maintained)
- [ ] XYO: bid-fill AS at t+1h did NOT drop below -0.50% at any point
- [ ] XYO: forced-close rate < 95%
- [ ] Total realized P&L across 30 days: positive (any positive)

**Kill if:** XYO bid-fill AS at t+1h < -0.50% at any weekly check, or
forced-close rate > 95% for 2 consecutive weeks. (Like SFP, XYO has no
negative-control analog to KAVA's "loses to random entry" flag — its deeper
validation cleared that check decisively — so no early-suspicion trigger beyond
the standard AS/forced-close stop conditions applies here yet.)

### GOAT decision — 2026-09-20 (30 days from 2026-08-21, its own clock)

**Proceed to capital ($200 GOAT, $50/fill) if:**
- [ ] GOAT: AS at t+1h > -0.15% × spread  (G4 maintained)
- [ ] GOAT: AS at t+4h > -0.30% × spread  (G5 maintained)
- [ ] GOAT: bid-fill AS at t+1h did NOT drop below -0.50% at any point
- [ ] GOAT: forced-close rate < 95%
- [ ] Total realized P&L across 30 days: positive (any positive)
- [ ] Mean net/forced-close has not stayed below -0.30% for 2+ consecutive
      weekly checks (registration-time watch item, see `docs/HANDOFF_GOATUSDT.md`)

**Kill if:** GOAT bid-fill AS at t+1h < -0.50% at any weekly check, or
forced-close rate > 95% for 2 consecutive weeks. Unlike SFP/XYO, GOAT's relayed
deep-validation numbers (93% vs 77%/37%) could not be independently verified by
this repo — no handoff artifact exists here — so this repo's own 30-day paper
trade carries more of the evidentiary weight for GOAT than it did for the other
three added pairs.

### XPR decision — 2026-09-20 (30 days from 2026-08-21, its own clock)

**Proceed to capital ($200 XPR, $50/fill) if:**
- [ ] XPR: AS at t+1h > -0.15% × spread  (G4 maintained)
- [ ] XPR: AS at t+4h > -0.30% × spread  (G5 maintained)
- [ ] XPR: bid-fill AS at t+1h did NOT drop below -0.50% at any point
- [ ] XPR: forced-close rate < 95%
- [ ] Total realized P&L across 30 days: positive (any positive)

**Kill if:** XPR bid-fill AS at t+1h < -0.50% at any weekly check, or
forced-close rate > 95% for 2 consecutive weeks. XPR had no watch items at
registration — the cleanest of the three pairs added 2026-08-21 — so no
additional early-suspicion trigger beyond the standard stop conditions.

### PIPPIN decision — 2026-09-20 (30 days from 2026-08-21, its own clock)

**Proceed to capital ($200 PIPPIN, $50/fill) if:**
- [ ] PIPPIN: AS at t+1h > -0.15% × spread  (G4 maintained)
- [ ] PIPPIN: AS at t+4h > -0.30% × spread  (G5 maintained)
- [ ] PIPPIN: bid-fill AS at t+1h did NOT drop below -0.50% at any point
- [ ] PIPPIN: forced-close rate < 95%
- [ ] Total realized P&L across 30 days: positive (any positive)
- [ ] Mean net/forced-close has not stayed below -0.30% for 2+ consecutive
      weekly checks (registration-time watch item — registered value
      -1.1084% is the worst in the pool; see `docs/HANDOFF_PIPPINUSDT.md`)

**Kill if:** PIPPIN bid-fill AS at t+1h < -0.50% at any weekly check, or
forced-close rate > 95% for 2 consecutive weeks. This pair carries the
heaviest registration-time watch item of the three added 2026-08-21.

### S decision — 2026-09-20 (30 days from 2026-08-21, its own clock)

**Proceed to capital ($200 S, $50/fill) if:**
- [ ] S: AS at t+1h > -0.15% × spread  (G4 maintained)
- [ ] S: AS at t+4h > -0.30% × spread  (G5 maintained)
- [ ] S: bid-fill AS at t+1h did NOT drop below -0.50% at any point
- [ ] S: forced-close rate < 95%
- [ ] Total realized P&L across 30 days: positive (any positive)
- [ ] Mean net/forced-close has not stayed below -0.30% for 2+ consecutive
      weekly checks, and ask-fill AS at t+1h has not deepened materially past
      its registered -0.1905% (registration-time watch items; see
      `docs/HANDOFF_SUSDT.md`)

**Kill if:** S bid-fill AS at t+1h < -0.50% at any weekly check, or
forced-close rate > 95% for 2 consecutive weeks. S has the thinnest
registered G3 margin (+14.9011%) of any pair added 2026-08-21.

### Combined capital cap

If MINA, SFP, XYO, GOAT, XPR, PIPPIN, and S all pass their respective
decisions: $200/pair, $50/fill, $1,400 total (KAVA excluded, already
suspended; CSPR and NIL excluded, both KILL on the external screen, not
onboarded). Any single pair passing alone still counts as meaningful
validation of the underlying hypothesis on its own.

---

## Results — MINA/KAVA (weekly append)

### Week 1 — 2026-08-14 to 2026-08-21

**2026-08-15:** KAVA/USDT suspended (`python3 src/paper_trade.py --suspend
KAVAUSDT`) on evidence from `liquidity_provision_v2/docs/FINAL_REPORT.md`
that its gate pass was a false positive — see "Status Update" at top of this
doc. MINA/USDT continues unaffected. Same day: SFPUSDT added to this paper
trade on its own independent clock — see "Results — SFP" below.

*Remaining weekly summary TBD — run `python src/paper_report.py` and paste here*

### Week 2 — 2026-08-21 to 2026-08-28

*TBD*

### Week 3 — 2026-08-28 to 2026-09-04

*TBD*

### Week 4 — 2026-09-04 to 2026-09-13

*TBD*

---

## Final Verdict — MINA/KAVA (2026-09-13)

*TBD*

---

## Results — SFP (weekly append, independent clock)

### Week 1 — 2026-08-15 to 2026-08-22

**2026-08-15:** SFPUSDT initialised (seed bar 2026-08-15T14:00:00Z, first
trading bar 2026-08-15T15:00:00Z). Registered gate re-run at this repo's flat
1.0% spread: 6/6 pass, 267 fills, near-zero bid/ask AS — see GATE.md.

**2026-08-20 (5.2 days in):** `src/paper_report.py` had a scaling bug in its
per-horizon AS gate labels — it compared the raw fraction AS mean against
percent-scale thresholds (a 100x mismatch), so the printed "PASS G4"/"PASS G5"
labels were almost always PASS regardless of the real value. Fixed (commit
617f203); the bid-fill-only auto-suspend check was already scaled correctly
and unaffected.

With the fix applied, **SFP is currently failing G4**: AS at t+1h = -0.2755%,
below the -0.15% maintenance threshold (was masked as a false PASS before the
fix). G5 still passes (-0.2556% vs -0.30%), and the bid-fill-only auto-suspend
check is nowhere close (-0.0611% vs -0.50% stop) — no auto-suspend triggers
from this.

**Same weekly check also shows mean net/forced close = -0.9894%**, past the
-0.30% stop-level guardrail in the Weekly Checks table above (19 forced
closes so far). This is the same underlying pattern as the G4 fail, not a
separate issue: SFP's forced closes are losing more, on average, than
completed round-trips earn (+1.0000% net each), so both should be reviewed
together over the next few weekly checks rather than treating G4 as an
isolated flag. Neither is an auto-suspend trigger on its own — SFP continues
running — but both warrant closer attention heading into Week 2.

*Remaining weekly summary TBD — run `python src/paper_report.py` and paste here*

### Week 2 — 2026-08-22 to 2026-08-29

*TBD*

### Week 3 — 2026-08-29 to 2026-09-05

*TBD*

### Week 4 — 2026-09-05 to 2026-09-14

*TBD*

---

## Final Verdict — SFP (2026-09-14)

*TBD*

---

## Results — XYO (weekly append, independent clock)

### Week 1 — 2026-08-20 to 2026-08-27

**2026-08-20:** XYOUSDT initialised (seed bar 2026-08-20T19:00:00Z, first
trading bar 2026-08-20T20:00:00Z). Registered gate re-run at this repo's flat
1.0% spread: 6/6 pass, 312 fills, positive bid/ask AS at t+1h — see GATE.md.
Verified via `--dry-run`/`--status` before and after that MINA's and SFP's
`start_date_utc` and live totals were untouched by the addition.

*Remaining weekly summary TBD — run `python src/paper_report.py` and paste here*

### Week 2 — 2026-08-27 to 2026-09-03

*TBD*

### Week 3 — 2026-09-03 to 2026-09-10

*TBD*

### Week 4 — 2026-09-10 to 2026-09-19

*TBD*

---

## Final Verdict — XYO (2026-09-19)

*TBD*

---

## Results — GOAT (weekly append, independent clock)

### Week 1 — 2026-08-21 to 2026-08-28

**2026-08-21:** GOATUSDT initialised (seed bar 2026-08-21T18:00:00Z, first
trading bar 2026-08-21T19:00:00Z). Registered gate re-run at this repo's flat
1.0% spread: 6/6 pass, 311 fills, positive bid/ask AS at t+1h and t+4h — see
GATE.md. Two watch items logged at registration (mean net/forced-close
-0.5043%, mild negative ask-fill AS asymmetry) — see
`docs/HANDOFF_GOATUSDT.md`. Verified via `--dry-run`/`--status` before and
after that MINA's, SFP's, and XYO's `start_date_utc` and live totals were
untouched by the addition.

*Remaining weekly summary TBD — run `python src/paper_report.py` and paste here*

### Week 2 — 2026-08-28 to 2026-09-04

*TBD*

### Week 3 — 2026-09-04 to 2026-09-11

*TBD*

### Week 4 — 2026-09-11 to 2026-09-20

*TBD*

---

## Final Verdict — GOAT (2026-09-20)

*TBD*

---

## Results — XPR (weekly append, independent clock)

### Week 1 — 2026-08-21 to 2026-08-28

**2026-08-21:** XPRUSDT initialised (seed bar 2026-08-21T21:00:00Z, first
trading bar 2026-08-21T22:00:00Z). Registered gate re-run at this repo's flat
1.0% spread: 6/6 pass, 249 fills, positive bid/ask AS at t+1h and t+4h, no
watch items — see GATE.md and `docs/HANDOFF_XPRUSDT.md`. Verified via
`--dry-run`/`--status` before and after that MINA's, SFP's, XYO's, and GOAT's
`start_date_utc` and live totals were untouched.

*Remaining weekly summary TBD — run `python src/paper_report.py` and paste here*

### Week 2 — 2026-08-28 to 2026-09-04

*TBD*

### Week 3 — 2026-09-04 to 2026-09-11

*TBD*

### Week 4 — 2026-09-11 to 2026-09-20

*TBD*

---

## Final Verdict — XPR (2026-09-20)

*TBD*

---

## Results — PIPPIN (weekly append, independent clock)

### Week 1 — 2026-08-21 to 2026-08-28

**2026-08-21:** PIPPINUSDT initialised (seed bar 2026-08-21T21:00:00Z, first
trading bar 2026-08-21T22:00:00Z). Registered gate re-run at this repo's flat
1.0% spread: 6/6 pass, 361 fills, in-bounds AS at t+1h and t+4h — see GATE.md
and `docs/HANDOFF_PIPPINUSDT.md`. Watch item logged at registration: mean
net/forced-close of -1.1084%, the worst in the pool. Verified via
`--dry-run`/`--status` before and after that MINA's, SFP's, XYO's, and GOAT's
`start_date_utc` and live totals were untouched.

*Remaining weekly summary TBD — run `python src/paper_report.py` and paste here*

### Week 2 — 2026-08-28 to 2026-09-04

*TBD*

### Week 3 — 2026-09-04 to 2026-09-11

*TBD*

### Week 4 — 2026-09-11 to 2026-09-20

*TBD*

---

## Final Verdict — PIPPIN (2026-09-20)

*TBD*

---

## Results — S (weekly append, independent clock)

### Week 1 — 2026-08-21 to 2026-08-28

**2026-08-21:** SUSDT initialised (seed bar 2026-08-21T21:00:00Z, first
trading bar 2026-08-21T22:00:00Z). Registered gate re-run at this repo's flat
1.0% spread: 6/6 pass, 248 fills, in-bounds blended AS at t+1h and t+4h — see
GATE.md and `docs/HANDOFF_SUSDT.md`. Watch items logged at registration:
pronounced ask-fill AS asymmetry (-0.1905% at t+1h) and elevated mean
net/forced-close (-0.6850%). Verified via `--dry-run`/`--status` before and
after that MINA's, SFP's, XYO's, and GOAT's `start_date_utc` and live totals
were untouched.

*Remaining weekly summary TBD — run `python src/paper_report.py` and paste here*

### Week 2 — 2026-08-28 to 2026-09-04

*TBD*

### Week 3 — 2026-09-04 to 2026-09-11

*TBD*

### Week 4 — 2026-09-11 to 2026-09-20

*TBD*

---

## Final Verdict — S (2026-09-20)

*TBD*

---

## Results — NIL (weekly append, independent clock)

### Week 1 — 2026-08-23 to 2026-08-30

**2026-08-23:** NILUSDT initialised (seed bar 2026-08-23T11:00:00Z, first
trading bar 2026-08-23T12:00:00Z). Registered gate re-run at this repo's flat
1.0% spread: 6/6 pass, 567 fills, blended AS in-bounds at t+1h and t+4h — see
GATE.md "Results — NILUSDT (verdict reversal)" and `docs/HANDOFF_NILUSDT.md`.
This is a **verdict reversal** — NIL was previously KILLed by an external
relay (2026-08-21 status update, alongside CSPRUSDT), reportedly on a
1-seed-of-30 statistical fluke, and reportedly retested clean at higher seed
counts; neither claim is independently reproducible from this repo, and
onboarding here rests solely on this repo's own reconciliation. Watch items
logged at registration, the loudest of any pair added so far: G4 margin only
0.0106pp above threshold, ask-fill AS@1h (-0.2752%) that would fail G4 in
isolation, and mean net/forced-close of -4.2899% (worst in the pool by ~4x).
Verified via `--dry-run`/`--status` before and after that every other pair's
`start_date_utc` and live totals were untouched.

*Remaining weekly summary TBD — run `python src/paper_report.py` and paste here*

### Week 2 — 2026-08-30 to 2026-09-06

*TBD*

### Week 3 — 2026-09-06 to 2026-09-13

*TBD*

### Week 4 — 2026-09-13 to 2026-09-22

*TBD*

---

## Final Verdict — NIL (2026-09-22)

*TBD*
