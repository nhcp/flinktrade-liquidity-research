# Crypto MM MEXC — Outcome Log
## append-only after each verdict

---

## 2026-08-20 — Cost-model audit (forced-close slippage, fee schedule, DCA parity gap analysis)

**Trigger:** Requested from outside this repo (FlinkTrade dashboard work surfacing
MINA/SFP/XYO's paper-trade numbers) — using FlinkTrade's DCA Bot cost model
(fee/slippage/spread/funding breakdown per trade) as the reference for what a
"complete" cost model looks like, and checking this repo's paper-trade P&L against
it. Investigation only — no code or state changed by this entry.

### 1. Forced-close slippage: confirmed unmodeled, now quantified

`paper_trade.py::process_pair_bars()` and `simulator.py::run_simulation()` both
exit forced closes at `exit_px = bar["close"]` exactly — the literal 1h bar close,
fee subtracted, **zero slippage**. This is not a paper-trade-only shortcut; it's
inherited directly from the backtest ("Fill detection mirrors the backtest
exactly" — paper_trade.py docstring). GATE.md's own "Critical Observations #2"
already flagged the qualitative risk ("OHLCV simulation forces all complete RTs
to return exactly spread_pct... Real fills would have noisy execution prices...
Treat Sharpe as direction correct, magnitude unreliable") but this was never
quantified in realized-P&L terms until now.

**Note this only applies to forced closes.** Complete round-trips (`COMPLETE_RT`)
are both legs resting maker limit orders — a limit order fills exactly at its
posted price or doesn't fill at all, so zero slippage on complete RTs is *correct*,
not a gap. The gap is specifically the forced-close exit leg, which is a taker
market order in reality.

**Diagnostic (read-only, live state untouched):** applied FlinkTrade DCA Bot's
per-leg `SLIPPAGE_RATE` (0.05%, `app/strategy_lab.py:25`) to each forced-close
exit leg only, recomputing cumulative `realized_pnl_pct_sum` retroactively as a
what-if:

| Pair | n trades | n forced | orig realized_pnl_pct_sum | with DCA-rate exit slippage | delta | win→loss flips |
|---|---|---|---|---|---|---|
| MINAUSDT | 33 | 13 | +15.1344% | +14.4844% | -0.6500pp | 0 |
| SFPUSDT | 42 | 20 | +2.6676% | +1.6676% | -1.0000pp (-37% of cumulative gain) | 1 |
| XYOUSDT | 1 | 0 | +1.0000% | +1.0000% | 0.0000pp | 0 |

SFP is the pair to watch: PAPER_TRADE.md's Week 1 SFP note already flagged mean
net/forced-close at -0.9894%, past the -0.30% guardrail, *before* any slippage
assumption is added. A further flat -0.05%/exit tax deepens an already-flagged
weakness, it doesn't create a new one.

**Caveat — this diagnostic is likely a floor, not an estimate.** DCA's 0.05% is
calibrated for BTC/ETH/SOL futures on Kraken, dramatically more liquid than MINA/
SFP/XYO spot on MEXC. PAPER_TRADE.md itself notes MINA's book was ~$2,600
USDT/hour volume at gate time. Real slippage on these specific thin books is
plausibly higher than 0.05%; getting an actual number needs either live execution
data (not obtainable from a paper trade that places no real orders) or MEXC L2
order-book depth analysis — that's capacity-at-scale work, appropriately scoped
to the Business Deployment Gate before any real capital, not a quick fix here.

### 2. MEXC fee schedule: re-verified live, still accurate

Checked MEXC's own published fee documentation plus independent third-party
sources (August 2026): 0% maker / 0.05% taker remains the current standard
base-tier spot rate, unchanged since this project's gate was registered
(2026-08-14). `MAKER_FEE`/`TAKER_FEE` constants in `paper_trade.py` and
`simulator.py` are accurate today, not just accurate at project start. (This is
the no-MX-token-discount base tier — correct assumption, since the paper account
holds no real MX balance to earn the 50% discount some sources mention.)

### 3. Gap inventory vs. DCA Bot's per-trade cost model

| DCA Bot has | This repo has | Gap? | Fixable now (a) | Needs new tracking / bigger work (b) |
|---|---|---|---|---|
| `fee_cost` per trade | Fee baked silently into `net_pct`, never broken out | Yes | (a) — fee is a known fixed constant per `event_type` (0% on complete-RT legs, 0.05% on forced-close exit only); 100% recoverable from `event_type` + `params` already logged, no new tracking | — |
| `slip_cost` per trade | Not modeled at all | Yes — real gap | A *labeled estimate* is displayable (as computed above) | (b) — an accurate number needs real fills or MEXC order-book depth for these specific pairs; belongs in Business Deployment Gate capacity testing |
| `spread_cost` (cost of crossing the spread) | N/A — mechanism is inverted: this strategy **is** the market maker, so the spread is its revenue, not a cost it pays | No — not applicable | — | — |
| `funding_cost` | N/A — MEXC spot has no funding fees (perpetuals-only concept) | No — not applicable | — | — |
| `gross_pnl` shown separately from net | Recoverable: `gross_pct = net_pct + known_fixed_fee` | Yes | (a) — trivial algebra from existing fields | — |
| Per-trade cost breakdown UI | Only one blended `net_pct` shown | Partial | (a) for fee/gross split | (b) for a *true* slippage line |

**Bottom line:** two of the gaps (per-trade fee split, gross vs. net split) are
pure display-layer recoveries from data already logged — no risk, no change to
`paper_trade.py`'s live calculation or any already-recorded number. The one real
gap (forced-close slippage) can only be *estimated* today, not fixed — a
trustworthy number requires new data this repo doesn't currently collect.
Retroactively changing `realized_pnl_pct_sum` to bake in an assumed slippage rate
would alter numbers already reported for MINA/SFP/XYO and was explicitly not
applied here pending confirmation.

**Action taken:** none — diagnostic only, `paper_trade_state.json` and
`paper_trade_events.csv` untouched. Proposed display-only additions (fee_cost,
gross_pct, and an optionally-labeled slippage-diagnostic column) reported back
for approval before any implementation.

---

## 2026-08-25T19:05:51.829014Z — Depth-realistic forced-close slippage diagnostic

Follow-up to the 2026-08-20 Cost-model audit entry above, which flagged DCA Bot's 0.05%/leg as "likely a floor, not an estimate" and recommended MEXC order-book depth analysis as the way to get an actual number. This entry is that analysis, computed by `src/slippage_model.py` (read-only diagnostic; no live state touched).

**Method:** for each live pair, walk the current order book (from `data/depth_snapshots.csv`, logged by `depth_logger.py`) to find the VWAP fill price for a $50 notional market order on the relevant side (bid side for a long's forced-close exit, ask side for a short's), average that slippage % across all available snapshots per pair, then apply it to every historical FORCED_CLOSE_BID/ASK event for that pair in `paper_trade_events.csv`.

**Caveat — read before trusting this number:** depth snapshots only exist from 2026-08-24 onward (PIPPINUSDT/NILUSDT) or from today, 2026-08-25 (the other 6 pairs — this task just turned on their depth logging). Historical forced closes go back to 2026-08-15, and there is no way to know what the book looked like at each fill's actual moment. This applies a current/recent depth estimate uniformly to the historical log — the same structural limitation as the DCA-rate diagnostic (a not-time-matched rate), improved by being grounded in this exchange's real depth for these specific pairs rather than borrowed from unrelated, more-liquid BTC/ETH/SOL futures pairs. MINA/SFP/XYO/GOAT/XPR/S rest on a single current snapshot each (order-of-magnitude read only); PIPPIN/NIL have ~30 hourly snapshots (more robust). Re-run this script periodically as depth_logger.py accumulates more history.

| Pair | n forced | orig realized_pnl_pct_sum | with depth-slippage | delta | win→loss flips | n snapshots |
|---|---|---|---|---|---|---|
| MINAUSDT | 18 | -21.5536% | -21.5536% | +0.0000pp | 0 | 1 |
| SFPUSDT | 26 | -28.8313% | -28.8313% | +0.0000pp | 0 | 1 |
| XYOUSDT | 5 | -8.9648% | -9.7761% | -0.8114pp | 0 | 1 |
| GOATUSDT | 5 | -12.6904% | -12.8431% | -0.1527pp | 0 | 1 |
| XPRUSDT | 15 | -0.8012% | -0.8408% | -0.0395pp | 0 | 1 |
| PIPPINUSDT | 7 | -15.1181% | -15.2462% | -0.1280pp | 0 | 30 |
| SUSDT | 8 | -12.9054% | -12.9269% | -0.0215pp | 0 | 1 |
| NILUSDT | 1 | -5.0474% | -5.0864% | -0.0390pp | 0 | 30 |

**Action taken:** none — diagnostic only, `paper_trade_state.json` and `paper_trade_events.csv` untouched.

---

## 2026-08-25T19:51:55Z — Toxic-flow stress test, original 7 MEXC live pairs

Full run of `src/toxic_flow_check.py` (see file docstring for method) across all seven original MEXC live pairs: MINAUSDT, SFPUSDT, XYOUSDT, GOATUSDT, XPRUSDT, PIPPINUSDT, SUSDT. Diagnostic-only — reads each pair's `data/<PAIR>_1h.csv`, does not touch `paper_trade_state.json`, `paper_trade_events.csv`, or any live pair's clock/state.

**Method:** for each pair, inject a synthetic 2σ/3σ/5σ permanent price-level shock (from the pair's own realized bar-return std dev) at a random point (seed=42) in its historical bar series, then re-run this repo's own fill/fee simulation logic on the whole post-shock series and check whether aggregate fill-adjusted monthly P&L stays positive.

| Pair | 2-sigma | 3-sigma | 5-sigma | Overall |
|---|---|---|---|---|
| MINAUSDT | PASS (25.35%/mo) | PASS (24.59%/mo) | PASS (22.54%/mo) | RESILIENT |
| SFPUSDT | PASS (57.27%/mo) | PASS (59.32%/mo) | PASS (54.53%/mo) | RESILIENT |
| XYOUSDT | PASS (79.98%/mo) | PASS (82.03%/mo) | PASS (81.31%/mo) | RESILIENT |
| GOATUSDT | PASS (60.93%/mo) | PASS (63.93%/mo) | PASS (58.14%/mo) | RESILIENT |
| XPRUSDT | PASS (78.15%/mo) | PASS (79.09%/mo) | PASS (79.96%/mo) | RESILIENT |
| PIPPINUSDT | PASS (51.46%/mo) | PASS (51.46%/mo) | PASS (49.88%/mo) | RESILIENT |
| SUSDT | PASS (13.34%/mo) | PASS (7.26%/mo) | PASS (14.90%/mo) | RESILIENT |

Summary: 7/7 pairs stay fill-adjusted-P&L-positive across all three synthetic shock sizes.

**Caveat:** this is a coarser proxy than a true "N round trips to recover" metric — a resilience signal, not a precise recovery-speed count (same caveat carried by the WEEX-repo version this was ported from). Bars are each pair's static `data/<PAIR>_1h.csv` pull from gate/onboarding time (mtimes span 2026-08-14 to 2026-08-21), not a fresh re-pull.

**Action taken:** none — diagnostic only, `paper_trade_state.json` and `paper_trade_events.csv` untouched.

---

## 2026-08-25T20:05:12Z — Wired depth-slippage + fill-probability into live P&L (paper_trade_state.json)

Follow-up to the full cost-component audit run earlier the same day, which found two gaps worth closing immediately: (1) `slippage_model.py` computed real depth-based slippage but `paper_trade.py` never imported it — the live-tracked numbers stayed zero-slippage; (2) `simulator.py`'s `FILL_RATE_HAIRCUT = 0.50` (flat, unexplained) only fed one derived backtest metric, never the actual live-tracked `realized_pnl_pct_sum` — every touch was credited as a 100% queue win. Both are now wired into `paper_trade.py`'s live run path, scoped to exactly the 8 live pairs (MINA/SFP/XYO/GOAT/XPR/PIPPIN/S/NIL; KAVAUSDT excluded, suspended). No cohort/hold-spread-matrix instance (300+ keys) is touched by any of this.

### What changed, mechanically

- **New `src/adjustment_model.py`**: adds a real fill-probability estimator (`p = avg_bar_volume_quote / (avg_bar_volume_quote + avg_resting_notional_at_level)`, from `depth_snapshots.csv` qty-at-level + `<PAIR>_1h.csv` turnover, clipped to [0.05, 0.95]), and reuses `slippage_model.py`'s already-verified snapshot/slippage functions directly (not duplicated). `p_complete = p_fill_bid × p_fill_ask` replaces the flat 0.50 for complete-RT weighting.
- **`paper_trade.py`**: `ps["totals"]` (raw, touch-rule P&L) is **byte-for-byte unchanged** — verified by diffing state before/after this deploy; every existing number matches exactly what it would have been with no code change. A new, purely additive `ps["totals_adjusted"]` tracks a combined-adjustment figure in parallel: complete-RT contributions are weighted by that pair's `fill_prob_complete`; forced-close contributions get the depth-based slippage adjustment (exit price walked through the real book instead of assumed at bar-close). A new `ps["adjustment_model"]` records the latest factors used and a depth-confidence label, refreshed every run.
- **One-time retroactive seed, applied once per pair (idempotent, verified by re-running twice — zero drift on the second run):** `ps["totals_adjusted"]` is seeded by replaying each pair's full event history through the *current* adjustment estimate — same "current estimate applied retroactively" approach the original slippage diagnostic used, now extended to fill-probability and actually wired into state instead of staying a side-channel report. Every subsequent run adds only that run's new events on top.
- **New `data/paper_trade_adjustments.csv`** (append-only, brand-new file — the existing `paper_trade_events.csv` schema was deliberately left untouched to avoid any risk to that file's parseability for the 300+ other tracked instances): one row per adjusted event, `event_id`-joinable back to the events ledger, tagged `is_retroactive_seed` True/False and carrying the depth-confidence label used at that moment.
- **`dashboard.py`**: added an "Adjusted net" column to the Live Research table (raw "Realized net" column unchanged, sitting right next to it), with a confidence chip and tooltip. Cohort tables untouched.
- **`paper_trade.py --status`**: now prints the adjusted line under each live pair's raw totals line.

### Design choice worth flagging: fill-probability is applied as an expected-value weight, not a stochastic gate

The fill-probability correction changes the **adjusted P&L figure**, not which touches actually fire as FILL_BID/FILL_ASK/COMPLETE_RT/FORCED_CLOSE events. The raw event stream — and therefore every pair's clock, its fill/RT/forced-close counts, and its `totals.realized_pnl_pct_sum` — is generated by the exact same untouched touch-rule logic as before. This was a deliberate choice: injecting randomness into which touches become real events would make runs non-deterministic and would be touching the gate/quoting machinery itself, which was explicitly out of scope. If a stricter model (literally dropping some fills) is wanted later, that's a bigger, separate change — flag it if that's the intent, this entry does not do that.

Forced closes get the slippage correction but NOT an additional fill-probability haircut — this mirrors `simulator.py`'s own precedent (its 0.50 haircut only ever applied to complete-RT frequency, forced closes counted at full weight as "already-realized outcomes"). Applying both corrections to both event types would double-count the same underlying "did this touch really happen" uncertainty; keeping them on separate event types keeps the two corrections orthogonal.

### Results — per pair (this run, 2026-08-25)

| Pair | raw realized_pnl_pct_sum | adjusted | delta | slippage component | fill-prob component | depth confidence |
|---|---|---|---|---|---|---|
| MINAUSDT | +53.4464% | +23.3414% | -30.1050pp | +0.0000pp | -30.1050pp | thin (3 snapshots) |
| SFPUSDT | +35.4429% | +14.4839% | -20.9590pp | -0.1265pp | -20.8325pp | thin (3 snapshots) |
| XYOUSDT | +52.0352% | +35.6506% | -16.3847pp | -0.8114pp | -15.5733pp | thin (3 snapshots) |
| GOATUSDT | +33.3096% | +28.5016% | -4.8080pp | -0.1298pp | -4.6782pp | thin (3 snapshots) |
| XPRUSDT | +9.1988% | +8.0523% | -1.1464pp | -0.1714pp | -0.9750pp | thin (3 snapshots) |
| PIPPINUSDT | +20.8024% | +17.0462% | -3.7562pp | -0.1487pp | -3.6075pp | **robust (32 snapshots)** |
| SUSDT | +20.0946% | +16.8663% | -3.2283pp | -0.0108pp | -3.2175pp | thin (3 snapshots) |
| NILUSDT | +23.9526% | +21.0856% | -2.8670pp | -0.0395pp | -2.8275pp | **robust (32 snapshots)** |

Every pair stays adjusted-P&L-positive. The fill-probability correction dominates the delta everywhere (as expected — complete RTs vastly outnumber forced closes for every live pair, so a per-pair queue-win probability applied to that volume has far more leverage than the slippage correction, which only touches the much smaller forced-close leg). Confirms the cost audit's finding that queue-position/fill-probability was the single largest unmodeled cost, not slippage.

### Honest limitations — read before treating "adjusted" as ground truth

1. **Fill-probability is a coarse proxy, not true queue position.** L2 depth snapshots show aggregate resting quantity at a price level, not individual order age or rank — there is no way to know, from public REST data, where a hypothetical new order would actually sit in the queue. The estimate here (resting depth vs. typical turnover, back-of-queue assumption) is defensible and data-grounded, but it is "better than an arbitrary flat 50%," not a real queue simulation.
2. **Depth-data confidence is genuinely thin for 6 of 8 pairs** (2-3 snapshots each, since depth logging for them only started 2026-08-25 — this task's own earlier work). Only PIPPIN/NIL (~32 hourly snapshots, logging since 2026-08-24) are "robust." Every adjusted number carries its confidence label in state, the dashboard, and the adjustments CSV — this is not silently presented as fully reliable.
3. **The retroactive seed applies a current estimate uniformly across each pair's full history**, not a time-matched reconstruction (the same structural limitation the original slippage diagnostic carried — there is no way to know what depth/turnover looked like at each historical event's actual moment). Going-forward events use whatever estimate was current at that run; the seed and the live increments are not computed the same way and are labeled accordingly (`is_retroactive_seed`) in the adjustments CSV.
4. Both corrections will self-improve with zero further code changes as `depth_logger.py` accumulates more snapshots — re-running `paper_trade.py` recomputes the estimate fresh every hour from whatever history exists at that moment (it is not cached/frozen at seed time).

### Verification performed before/after this deploy

- `ps["totals"]` diffed old vs. new state: every pair's raw fills/complete_rts/forced_closes/realized_pnl_pct_sum changed by exactly what this run's new bar processing produced, nothing more — confirmed byte-for-byte against a pre-change backup.
- `paper_trade_events.csv` diffed old vs. new: all pre-existing rows byte-identical; only new rows appended.
- Ran twice back-to-back: second run produced zero change to `totals_adjusted` (no new bars, seed correctly skipped as already-present) — confirms idempotency, no double-counting risk from repeated hourly cron runs.
- `--dry-run` tested first (no writes) before the real run that actually seeded state.

**Action taken:** `paper_trade_state.json` gained new, additive fields per live pair (`totals_adjusted`, `adjustment_model`); no existing field's value was altered. `paper_trade_events.csv` unchanged in every pre-existing row. New file `data/paper_trade_adjustments.csv` created. No pair's clock, fill/RT/forced-close event stream, or gate/quoting logic was modified.
