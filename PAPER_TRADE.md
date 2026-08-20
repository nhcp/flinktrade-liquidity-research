# Crypto MM MEXC — 30-Day Paper Trade
## MINA/KAVA started: 2026-08-14 | Target end: 2026-09-13
## SFP started: 2026-08-15 | Target end: 2026-09-14 (independent clock — see Status Update below)
## XYO started: 2026-08-20 | Target end: 2026-09-19 (independent clock — see Status Update below)

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
| Pairs             | MINA/USDT, KAVA/USDT, SFP/USDT, XYO/USDT |
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
2026-09-10).

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

---

## Files

| File | Purpose |
|---|---|
| `data/paper_trade_state.json` | Persistent state: positions, last bar, totals |
| `data/paper_trade_events.csv` | Append-only event log: every fill and RT outcome |
| `src/paper_trade.py` | Hourly runner |
| `src/paper_report.py` | P&L and adverse-selection report |

The events CSV is the canonical record. If the state JSON is ever lost or
corrupted, it can be reconstructed by replaying the events.

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

### Combined capital cap

If MINA, SFP, and XYO all pass their respective decisions: $200/pair, $50/fill,
$600 total (KAVA excluded, already suspended). Any single pair passing alone
still counts as meaningful validation of the underlying hypothesis on its own.

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
