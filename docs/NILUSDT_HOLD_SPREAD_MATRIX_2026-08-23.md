# NILUSDT Hold/Spread-Width Matrix — Forward Test (started 2026-08-23)

## What this is

A 10-instance forward (out-of-sample) test of S8 (liquidity provision)
max-hold-window sensitivity, crossed with the two most relevant spread
widths, scoped to **NILUSDT only**, run alongside — and completely separate
from — all three of:

- the 9 live paper-trade pairs (still at each pair's own original hold/
  spread and start date; NIL's live pair still at 3h hold / 1.0% spread /
  2026-08-23T12:13:55Z start),
- the existing 42-instance spread-width cohort
  (`docs/SPREAD_WIDTH_COHORT_2026-08-22.md`), and
- the existing 70-instance hold/spread-width matrix
  (`docs/HOLD_SPREAD_MATRIX_2026-08-23.md`, 7 pairs x 5 holds x 2 widths) —
  NIL was **not** part of that matrix's `HOLD_SPREAD_BASE_PAIRS` for the
  same reason it wasn't in the spread-width cohort: it joined live paper
  trade after that matrix's pair list was fixed.
- NIL's own 6-instance spread-width cohort
  (`docs/NILUSDT_SPREAD_WIDTH_COHORT_2026-08-23.md`, started the same day)
  — a different variable (hold window, not just width), different keys,
  no shared state.

**Design: 1 pair (NILUSDT) x 5 max-hold windows x 2 spread widths, same
convention as the original 70-instance matrix, own independent clock.**

| Hold window | Bars | Purpose |
|---|---|---|
| 1h | 1 | shortest — high end of forced-close rate, cheapest per-trade exposure |
| 2h | 2 | short |
| 3h | 3 | current live baseline hold |
| 4h | 4 | long |
| 6h | 6 | longest tested — lowest forced-close rate, highest exposure per trade |

| Spread width | Purpose |
|---|---|
| 1.0% | current live baseline width |
| 0.9% | narrowest width carried over as non-disqualifying from the original spread-width cohort's design (see `docs/SPREAD_WIDTH_COHORT_2026-08-22.md`) |

10 = 1 pair x 5 holds x 2 widths.

## Why this exists

Same motivation as the original 70-instance matrix (see
`docs/HOLD_SPREAD_MATRIX_2026-08-23.md` "Why this exists"): a hold-window
backtest sweep on a single fixed historical window can't distinguish
genuine hold-window edge from overfitting to that window. NIL wasn't
included in the original matrix because it wasn't live yet when that
matrix's pair list was fixed. NIL is a particularly relevant pair to test
this on: its live registration already carries the **worst forced-close
severity in the entire pool by ~4x** (-4.2899% mean net/forced-close at the
current 3h/1.0% baseline — see `docs/HANDOFF_NILUSDT.md`), and the original
matrix's backtest finding was that **longer holds tend to worsen
forced-close severity even as headline P&L improves** on most pairs (5 of
7). Whether that pattern holds, worsens further, or reverses for NIL
specifically — the pair already flagged as the pool's severity outlier — is
a materially more urgent question for NIL than it was for any of the
original 7.

## Identity scheme

Each instance is keyed in `data/paper_trade_state.json`'s `pairs` dict by
`NILUSDT-WIDTH-Nh`, reusing the exact same `hold_spread_instance_id()`
convention as the original 70-instance matrix:

```
NILUSDT-1.0-1h   NILUSDT-1.0-2h   NILUSDT-1.0-3h   NILUSDT-1.0-4h   NILUSDT-1.0-6h
NILUSDT-0.9-1h   NILUSDT-0.9-2h   NILUSDT-0.9-3h   NILUSDT-0.9-4h   NILUSDT-0.9-6h
```

These keys never collide with anything else in `state["pairs"]`: the bare
`NILUSDT` key (the live pair), NIL's own spread-width cohort keys
(`NILUSDT-0.5` .. `NILUSDT-1.0-FRESH`, no `-Nh` suffix), or the original
70-instance matrix's keys (all `SYMBOL-WIDTH-Nh` for `SYMBOL` in
`{MINA,SFP,XYO,GOAT,XPR,PIPPIN,S}USDT` — NIL is not among them).

## Mechanics / implementation notes

- `src/paper_trade.py`: new module-level dict `NIL_HOLD_SPREAD_INSTRUMENTS`
  (built from the same `HOLD_SPREAD_WIDTHS` / `HOLD_SPREAD_HOLDS` constants
  and the same `hold_spread_instance_id()` helper as the original matrix,
  applied to `NILUSDT` only) and a dedicated run function
  `cmd_run_nil_hold_spread_cohort()`, deliberately not sharing code paths
  with `cmd_run_hold_spread_cohort()` (the original matrix's runner) —
  only the lower-level, already-generic `_run_hold_spread_instance_on_bars()`
  helper is reused.
- One kline fetch (NILUSDT only) is fanned out to all 10 hold x width
  variants, each with its own fully independent state.
- Verified end-to-end before deployment, same practice as every other
  cohort build in this repo:
  - `--dry-run` full run with zero writes — `sha256sum` of both state and
    events files identical before and after.
  - A live run then seeded all 10 new instances (`start_date_utc` =
    `2026-08-23T16:34:54Z` for all 10 — the same run that also seeded NIL's
    6-instance spread-width cohort above) while a before/after diff of the
    full state file confirmed: all 122 pre-existing `pairs` entries
    byte-identical; exactly 16 new keys added total (6 spread-width + 10
    hold/spread), matching `NIL_SPREAD_COHORT_INSTRUMENTS` and
    `NIL_HOLD_SPREAD_INSTRUMENTS` precisely; events CSV grew by zero rows.
  - A follow-up `--dry-run` confirmed idempotency.
- New CLI: `python src/paper_trade.py --status-nil-hold-spread` (read-only).
  `--suspend`/`--resume` also accept this cohort's instance IDs (e.g.
  `--suspend NILUSDT-0.9-1h`) — the existing case-insensitive resolution
  logic (`_resolve_instance_arg`, added for the original matrix's
  lowercase `-Nh` suffix) applies unchanged.
- Runs on the existing hourly cron entry — no new cron job added.

## Decision framework

This cohort is diagnostic, same as the original matrix. No live pair's
`MAX_HOLD_BARS` or `SPREAD_PCT` changes based on early cohort results.

**Planned re-check window: 2026-09-12 to 2026-09-22** (matching the original
matrix's re-check window, so NIL's own results can be read alongside it).
At that point, per hold/width cell: fill-adjusted net over the shared
window, complete-RT vs. forced-close count per hold window, and — most
importantly for NIL specifically — mean net per forced close per hold
window, to see whether NIL's already-worst-in-pool severity worsens
further at longer holds (as it did for 5 of 7 pairs in the original
matrix's backtest) or behaves differently.
