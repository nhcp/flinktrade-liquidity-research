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
