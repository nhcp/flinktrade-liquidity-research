# Spread-Width Cohort — Forward Test (started 2026-08-22)

## What this is

A 42-instance forward (out-of-sample) test of S8 (liquidity provision)
spread-width sensitivity, run alongside — and completely separate from — the
7 original live paper-trade pairs (MINA, SFP, XYO, GOAT, XPR, PIPPIN, S,
each still running at their original 1.0% spread and original start date,
untouched by this cohort).

**Design: 7 pairs x 6 widths, all starting the same day.**

| Width | Purpose |
|---|---|
| 0.5% | narrower — high end of fill-frequency gain |
| 0.6% | narrower |
| 0.7% | narrower |
| 0.8% | narrower |
| 0.9% | narrower — closest to baseline |
| 1.0% (fresh control) | same width as the live pairs, but a brand-new clock starting today |

42 = 7 pairs × 6 widths.

## Why this exists

Two prior single-window backtests (2026-08-22) swept spread width on the
same ~20-day historical window used to register every pair's live 1.0% gate:

- **Wide sweep (2%-5%):** fill-adjusted monthly return decayed
  monotonically with width on 5/7 pairs — 1.0% outperformed decisively.
- **Narrow sweep (0.5%-0.9%):** the opposite pattern — 6/7 pairs had a
  narrower width that *beat* the 1.0% baseline, several by a wide margin
  (XYO +91% relative at 0.6%, MINA +87% at 0.5%).

Both sweeps used the exact same 20.8-day historical window. That's the gap
this cohort is built to close: **a result that only holds on one fixed
historical window is not distinguishable from overfitting to that window.**
Two specific findings from the narrow sweep make this concrete:

- **XYO's apparent gain was traced to a mechanical artifact of that one
  window**: at 0.5-0.6% width, XYO's forced-close rate happened to be
  near-zero (4 forced closes out of 722 fills) in that specific 20 days —
  which is what drove the outsized return, not necessarily a durable
  property of narrower spreads on XYO.
- **PIPPIN's headline P&L looked better narrower, but its actual risk
  metric got worse**: mean net per forced close *worsened* monotonically
  as spread narrowed (-2.74% at 0.5% vs. -1.11% at the already-flagged-bad
  1.0% baseline). The positive headline number in the narrow sweep was
  carried entirely by a falling forced-close *rate*, not falling
  forced-close *severity* — exactly the kind of result that looks good in
  a backtest until a bad week of real fills.

A backtest re-run on the same window can't distinguish "genuine spread-width
edge" from "this window happened to have few adverse price swings at this
width." Only forward, out-of-sample data can. This cohort exists to get
that data, under conditions designed to isolate the one variable in
question.

## Design principles

1. **Width is the only variable.** Every instance uses identical mechanics
   to the 7 live pairs and to each other: `NOTIONAL_USDT = $50`,
   `MAX_HOLD_BARS = 3` (3h forced-close window), 0% maker / 0.05% taker MEXC
   fee schedule, same OHLCV-touch fill detection. Only `SPREAD_PCT` differs
   per width group.

2. **Same start date for all 42, including a fresh 1.0% control.** All 42
   instances seeded on the same run (2026-08-22, first trading bar
   2026-08-22T18:00:00Z) — this is what makes the 6 widths comparable to
   *each other* (no width gets a head start or a different slice of market
   conditions). The 1.0%-fresh group is not redundant with the live 1.0%
   pairs: it exists specifically so that if forward results diverge from
   the two backtest sweeps, we can tell whether that's a **width effect**
   (fresh-1.0% differs from fresh-0.5%..0.9%, all measured over the same
   calendar days) or a **time-period effect** (fresh-1.0% differs from the
   original 1.0% pairs, which started on different, earlier dates
   2026-08-15..2026-08-21 and have already lived through different market
   conditions). Without the fresh control, any divergence between "narrower
   looked better in the backtest" and "narrower looks worse forward" would
   be confounded with the fact that forward data is simply a later, disjoint
   time period than the original 1.0% pairs' history.

3. **Complete isolation from the 7 live pairs.** See Identity Scheme below —
   distinct state keys, no shared mutable state, verified byte-identical
   before/after on the original 7's data.

## Identity scheme

Each instance is keyed in `data/paper_trade_state.json`'s `pairs` dict by
`SYMBOL-WIDTH`, distinct from the bare-symbol keys (`MINAUSDT`, `SFPUSDT`,
etc.) used by the 7 original live pairs:

```
MINAUSDT-0.5   MINAUSDT-0.6   MINAUSDT-0.7   MINAUSDT-0.8   MINAUSDT-0.9   MINAUSDT-1.0-FRESH
SFPUSDT-0.5    SFPUSDT-0.6    SFPUSDT-0.7    SFPUSDT-0.8    SFPUSDT-0.9    SFPUSDT-1.0-FRESH
XYOUSDT-0.5    XYOUSDT-0.6    XYOUSDT-0.7    XYOUSDT-0.8    XYOUSDT-0.9    XYOUSDT-1.0-FRESH
GOATUSDT-0.5   GOATUSDT-0.6   GOATUSDT-0.7   GOATUSDT-0.8   GOATUSDT-0.9   GOATUSDT-1.0-FRESH
XPRUSDT-0.5    XPRUSDT-0.6    XPRUSDT-0.7    XPRUSDT-0.8    XPRUSDT-0.9    XPRUSDT-1.0-FRESH
PIPPINUSDT-0.5 PIPPINUSDT-0.6 PIPPINUSDT-0.7 PIPPINUSDT-0.8 PIPPINUSDT-0.9 PIPPINUSDT-1.0-FRESH
SUSDT-0.5      SUSDT-0.6      SUSDT-0.7      SUSDT-0.8      SUSDT-0.9      SUSDT-1.0-FRESH
```

The `-1.0-FRESH` suffix (vs. bare `1.0` for the other widths) exists because
`SYMBOLUSDT-1.0` would otherwise collide conceptually with the live pair at
the same width — the suffix makes explicit that this is the *new, separate*
control-group clock, not the original pair.

Both the original 7 and the 42 cohort instances live in the same
`state["pairs"]` dict (per the original task spec — "distinct keys," not a
separate JSON section), but the key namespaces never overlap, and
`src/paper_trade.py`'s original per-pair processing loop (the one driving
the 7 live pairs) was left completely unmodified — cohort instances are
processed by a separate function (`cmd_run_cohorts`) added after it, reading
and writing only `state["pairs"][<cohort instance id>]`.

## Mechanics / implementation notes

- `src/paper_trade.py`: `process_pair_bars()` gained an optional
  `spread_pct` parameter (default = the existing global `SPREAD_PCT`, so the
  7 live pairs' call site is unchanged and their behavior is provably
  identical to before). Cohort instances pass their own width explicitly.
- To avoid 42 redundant hourly API calls, klines are fetched **once per
  underlying symbol** (7 fetches) and fanned out to that symbol's 6
  width-variants, each of which still has its own fully independent
  `pending_bid`/`pending_ask`/`totals`/`start_date_utc` state — there is no
  shared mutable state between width-variants beyond the read-only bar data
  itself.
- Verified end-to-end before deployment: `--dry-run` full run (49 total
  instances, 14 API fetches, ~9s) with zero writes (state file hash
  unchanged); a live run showed the original 7 pairs' state advancing
  exactly as normal hourly cron operation would (one new bar, one new
  complete RT on MINA/XYO — unrelated to this change); all 42 cohort
  instances seeded with `start_date_utc` = the same run timestamp; a
  second consecutive run correctly found "no new bars" for all 49
  instances (idempotent, matching the existing documented guarantee for
  the original pairs).
- New CLI: `python src/paper_trade.py --status-cohort` (read-only, grouped
  by width) and `--suspend`/`--resume` now also accept cohort instance IDs
  (e.g. `--suspend PIPPINUSDT-0.5`) in addition to the original 7 pair
  symbols.
- Runs on the existing hourly cron entry (`5 * * * * ... src/paper_trade.py`)
  — no new cron job was added; one run now processes all 49 instances.

## PIPPIN risk flag

PIPPIN is tagged in every width cohort (CLI `--status-cohort` and the local
dashboard) with:

> Known risk: forced-close severity worsens at narrower spreads (backtest
> finding)

This is a carry-forward warning, not a live measurement — it's the
narrow-sweep backtest finding above, attached so that an early good-looking
result on PIPPIN's narrower-width instances doesn't get over-trusted before
enough forced-close events have actually occurred forward to confirm or
refute it one way or the other.

## Decision framework

This cohort is diagnostic. No live pair's `SPREAD_PCT` changes based on
backtest sweeps or on early cohort results — see the two sweep reports for
that explicit instruction, which applies here too.

**Planned re-check date: 2026-09-15 to 2026-09-21 (24-30 days from
2026-08-22).** At that point, per width group and per pair, check:

- Fill-adjusted monthly net (or simple realized P&L over the window, since
  all 42 share a start date and can be compared directly without
  annualizing)
- Complete-RT count vs. forced-close count (fill frequency)
- Mean net per forced close, specifically for PIPPIN across all 6 widths —
  does the narrow-sweep finding (severity worsens narrower) replicate
  forward, or was it also a single-window artifact?
- Whether the fresh-1.0%-control group tracks the original 1.0% live pairs
  closely (expected, if there's no strong time-period effect) or diverges
  (would indicate the market regime shifted meaningfully since the pairs'
  original start dates, and any width comparison needs to control for that)

Only after that check — with real forward fill data, not another replay of
the same 20-day window — should any live `SPREAD_PCT` change be considered.
