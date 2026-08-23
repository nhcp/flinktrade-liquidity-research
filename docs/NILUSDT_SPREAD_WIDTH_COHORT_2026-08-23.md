# NILUSDT Spread-Width Cohort — Forward Test (started 2026-08-23)

## What this is

A 6-instance forward (out-of-sample) test of S8 (liquidity provision)
spread-width sensitivity, scoped to **NILUSDT only**, run alongside — and
completely separate from — both:

- the 9 live paper-trade pairs (MINA, KAVA, SFP, XYO, GOAT, XPR, PIPPIN, S,
  NIL — NIL itself still running unmodified at its original 1.0% spread and
  original 2026-08-23T12:13:55Z start, see `docs/HANDOFF_NILUSDT.md`), and
- the existing 42-instance spread-width cohort
  (`docs/SPREAD_WIDTH_COHORT_2026-08-22.md`, 7 pairs x 6 widths, started
  2026-08-22) — NIL was **not** part of that cohort's `COHORT_BASE_PAIRS`
  (NIL joined live paper trade the day after that cohort launched), so this
  is a new, clearly separate group, not an addition to the existing one.

**Design: 1 pair (NILUSDT) x 6 widths, same convention as the original
cohort, own independent clock.**

| Width | Purpose |
|---|---|
| 0.5% | narrower — high end of fill-frequency gain |
| 0.6% | narrower |
| 0.7% | narrower |
| 0.8% | narrower |
| 0.9% | narrower — closest to baseline |
| 1.0% (fresh control) | same width as NIL's live pair, but a brand-new clock starting today |

6 = 1 pair x 6 widths.

## Why this exists

Same motivation as the original 42-instance cohort (see
`docs/SPREAD_WIDTH_COHORT_2026-08-22.md` "Why this exists"): a spread-width
backtest sweep on a single fixed historical window can't distinguish genuine
width edge from overfitting to that window's specific price action. NIL
wasn't included in the original cohort because it wasn't live yet at the
time that cohort launched (it was onboarded 2026-08-23 as a verdict
reversal — see `docs/HANDOFF_NILUSDT.md`). NIL is also the least
comfortable pass registered in this repo to date (thinnest G4 margin,
worst-in-pool forced-close severity, asymmetric ask-side toxic-flow signal —
see HANDOFF_NILUSDT.md "Gate metrics that justified reversing the verdict"),
which makes width sensitivity a more consequential question for this pair
than for most others in the pool.

## Identity scheme

Each instance is keyed in `data/paper_trade_state.json`'s `pairs` dict by
`NILUSDT-WIDTH`, reusing the exact same `cohort_instance_id()` convention as
the original 7-pair cohort:

```
NILUSDT-0.5   NILUSDT-0.6   NILUSDT-0.7   NILUSDT-0.8   NILUSDT-0.9   NILUSDT-1.0-FRESH
```

These keys never collide with anything else in `state["pairs"]`: the bare
`NILUSDT` key (the live pair), or any of the original cohort's keys (which
are all `SYMBOL-WIDTH` for `SYMBOL` in `{MINA,SFP,XYO,GOAT,XPR,PIPPIN,S}USDT`
— NIL is not among them).

## Mechanics / implementation notes

- `src/paper_trade.py`: new module-level dict `NIL_SPREAD_COHORT_INSTRUMENTS`
  (built from the same `COHORT_WIDTHS` / `COHORT_FRESH_CONTROL_WIDTH`
  constants and the same `cohort_instance_id()` helper as the original
  cohort, applied to `NILUSDT` only) and a dedicated run function
  `cmd_run_nil_spread_cohort()`, deliberately not sharing code paths with
  `cmd_run_cohorts()` (the original 7-pair cohort's runner) or the main
  9-pair loop — only the lower-level, already-generic
  `_run_cohort_instance_on_bars()` helper is reused, since it takes no
  reference to any cohort-specific global dict.
- One kline fetch (NILUSDT only) is fanned out to all 6 width variants, each
  with its own fully independent `pending_bid`/`pending_ask`/`totals`/
  `start_date_utc` state.
- Verified end-to-end before deployment:
  - `--dry-run` full run with zero writes — `sha256sum` of
    `data/paper_trade_state.json` and `data/paper_trade_events.csv`
    identical before and after.
  - A live run then seeded all 6 new instances (`start_date_utc` =
    `2026-08-23T16:34:54Z` for all 6) while a before/after diff of the full
    state file confirmed: all 122 pre-existing `pairs` entries (9 live
    pairs including bare `NILUSDT` + 42 original spread-width cohort + 70
    original hold/spread matrix + 1 leftover `ETHWUSDT` entry)
    byte-identical; exactly 6 new keys added, matching
    `NIL_SPREAD_COHORT_INSTRUMENTS` precisely; events CSV grew by zero rows
    (seeding a fresh instance emits no events, same as the original
    cohort's documented launch behavior).
  - A follow-up `--dry-run` confirmed idempotency: state hash after the
    seed run stayed fixed under a further dry pass.
- New CLI: `python src/paper_trade.py --status-nil-cohort` (read-only,
  grouped list, does not touch the original cohort's status output).
  `--suspend`/`--resume` also accept this cohort's instance IDs (e.g.
  `--suspend NILUSDT-0.5`).
- Runs on the existing hourly cron entry — no new cron job added.

## Decision framework

This cohort is diagnostic, same as the original. No live pair's
`SPREAD_PCT` changes based on early cohort results.

**Planned re-check window: 2026-09-15 to 2026-09-22** (roughly matching the
original cohort's re-check window, so NIL's own results can be read
alongside it). At that point, per width: fill-adjusted net over the shared
window, complete-RT vs. forced-close count, and — given NIL's flagged
forced-close severity risk (worst in the pool at 1.0%, -4.2899% mean
net/forced-close) — whether that severity improves, worsens, or holds
roughly steady at narrower widths, the same question the original cohort is
answering for its 7 pairs.
