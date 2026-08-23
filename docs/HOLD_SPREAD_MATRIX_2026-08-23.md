# Hold/Spread-Width Matrix — Forward Test (started 2026-08-23)

## What this is

A 70-instance forward (out-of-sample) test of S8 (liquidity provision)
max-hold-window sensitivity, crossed with the two most relevant spread
widths, run alongside — and completely separate from — the 7 original live
paper-trade pairs (MINA, SFP, XYO, GOAT, XPR, PIPPIN, S, still at their
original 3h hold / 1.0% spread and original start dates) **and** the
42-instance spread-width cohort (docs/SPREAD_WIDTH_COHORT_2026-08-22.md,
still at its original 3h hold, 0.5–0.9%/1.0%-FRESH spreads, started
2026-08-22).

**Design: 7 pairs x 5 max-hold windows x 2 spread widths, all starting the
same day (today).**

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
| 0.9% | narrowest width that stayed non-disqualifying in the prior spread-width backtest sweep (docs/SPREAD_WIDTH_COHORT_2026-08-22.md) |

70 = 7 pairs × 5 holds × 2 widths.

## Why this exists

A backtest sweep of `max_hold_bars` (`src/simulator.py --max-hold`) over the
same ~20-day historical window used to register every pair's live gate shows
a pattern structurally identical to the spread-width backtest that motivated
the prior cohort:

**Headline P&L (fill-adjusted monthly net) improves monotonically, or close
to it, with longer holds on all 7 pairs.** Longer holds mean fewer forced
closes (a forced close only fires once a position ages past the hold
window without the other side filling), and each forced close carries a
0.05% taker fee plus, more importantly, whatever adverse price move
accumulated over the hold — so trading fewer of them looks strictly better
in the P&L headline:

| Pair | fill-adj monthly% @1h | @6h |
|---|---|---|
| MINAUSDT | -22.42% | +56.03% |
| SFPUSDT | -22.36% | +88.49% |
| XYOUSDT | +9.73% | +100.91% |
| GOATUSDT | -23.24% | +94.06% |
| XPRUSDT | +88.61% | +84.53% |
| PIPPINUSDT | -128.91% | +105.33% |
| SUSDT | -73.41% | +68.07% |

**But forced-close severity — the mean net P&L of the forced closes that
still do happen — worsens on 5 of 7 pairs as the hold window lengthens**,
comparing the shortest (1h) to the longest (6h) tested window:

| Pair | mean forced-close net% @1h | @6h | n forced @6h | direction |
|---|---|---|---|---|
| MINAUSDT | -0.0966% | -0.2822% | 13 | **worsens** |
| SFPUSDT | -0.1101% | -0.0130% | 13 | improves |
| XYOUSDT | -0.0524% | -0.3696% | 11 | **worsens** |
| GOATUSDT | -0.1099% | -0.4830% | 11 | **worsens** |
| XPRUSDT | +0.1684% | +0.2723% | 15 | improves |
| PIPPINUSDT | -0.3487% | -1.4376% | 8 | **worsens** |
| SUSDT | -0.2134% | -0.7016% | 14 | **worsens** |

This is the same shape as the narrow-sweep spread-width finding: **the
positive headline number is carried by a falling forced-close rate, not by
falling (or even flat) forced-close severity.** A longer hold gives an
adverse move more time to develop before the exit is forced, so on most
pairs the forced closes that do still happen are worse ones, on average,
even though there are fewer of them. PIPPIN is again the sharpest case
(-0.35% → -1.44% mean forced-close net, in line with its already-flagged
narrower-spread severity problem) — the same kind of tail risk that looks
fine in an aggregate monthly number until a bad week of real fills lands on
one of the now-rarer, now-larger forced closes.

A backtest re-run on the same fixed 20-day window can't distinguish
"genuine hold-window edge" from "this window happened to have few adverse
swings big enough to matter within a longer hold." Only forward,
out-of-sample data can — which is exactly what this cohort is built to
collect, under conditions that isolate hold window and spread width as the
only two variables in question.

## Design principles

1. **Hold window and spread width are the only variables.** Every instance
   uses identical mechanics to the 7 live pairs and to each other:
   `NOTIONAL_USDT = $50`, 0% maker / 0.05% taker MEXC fee schedule, same
   OHLCV-touch fill detection. Only `MAX_HOLD_BARS` and `SPREAD_PCT` differ
   per instance.

2. **Same start date for all 70.** All 70 instances seeded on the same run
   (2026-08-23T11:28:36Z) — this is what makes the 5 hold windows and 2
   widths comparable to each other, with no group getting a head start or a
   different slice of market conditions. This cohort does not need a
   separate "fresh 1.0%" control the way the spread-width cohort did: its
   own 1.0%/3h cell is already a fresh, same-day-started replica of the live
   pairs' params, serving that role directly.

3. **Complete isolation from the 7 live pairs and the 42-instance
   spread-width cohort.** See Identity Scheme below — distinct state keys,
   no shared mutable state, verified byte-identical before/after on all 51
   pre-existing state entries (7 live pairs + 42 spread-width cohort + 1
   leftover rejected-candidate entry, ETHWUSDT, also untouched).

## Identity scheme

Each instance is keyed in `data/paper_trade_state.json`'s `pairs` dict by
`SYMBOL-WIDTH-Nh`, distinct from both the bare-symbol keys (`MINAUSDT`,
`SFPUSDT`, etc.) used by the 7 live pairs and the `SYMBOL-WIDTH` /
`SYMBOL-1.0-FRESH` keys used by the spread-width cohort:

```
MINAUSDT-1.0-1h  MINAUSDT-1.0-2h  MINAUSDT-1.0-3h  MINAUSDT-1.0-4h  MINAUSDT-1.0-6h
MINAUSDT-0.9-1h  MINAUSDT-0.9-2h  MINAUSDT-0.9-3h  MINAUSDT-0.9-4h  MINAUSDT-0.9-6h
SFPUSDT-1.0-1h   SFPUSDT-1.0-2h   SFPUSDT-1.0-3h   SFPUSDT-1.0-4h   SFPUSDT-1.0-6h
SFPUSDT-0.9-1h   SFPUSDT-0.9-2h   SFPUSDT-0.9-3h   SFPUSDT-0.9-4h   SFPUSDT-0.9-6h
XYOUSDT-1.0-1h   XYOUSDT-1.0-2h   XYOUSDT-1.0-3h   XYOUSDT-1.0-4h   XYOUSDT-1.0-6h
XYOUSDT-0.9-1h   XYOUSDT-0.9-2h   XYOUSDT-0.9-3h   XYOUSDT-0.9-4h   XYOUSDT-0.9-6h
GOATUSDT-1.0-1h  GOATUSDT-1.0-2h  GOATUSDT-1.0-3h  GOATUSDT-1.0-4h  GOATUSDT-1.0-6h
GOATUSDT-0.9-1h  GOATUSDT-0.9-2h  GOATUSDT-0.9-3h  GOATUSDT-0.9-4h  GOATUSDT-0.9-6h
XPRUSDT-1.0-1h   XPRUSDT-1.0-2h   XPRUSDT-1.0-3h   XPRUSDT-1.0-4h   XPRUSDT-1.0-6h
XPRUSDT-0.9-1h   XPRUSDT-0.9-2h   XPRUSDT-0.9-3h   XPRUSDT-0.9-4h   XPRUSDT-0.9-6h
PIPPINUSDT-1.0-1h  ...            PIPPINUSDT-1.0-6h
PIPPINUSDT-0.9-1h  ...            PIPPINUSDT-0.9-6h
SUSDT-1.0-1h     SUSDT-1.0-2h     SUSDT-1.0-3h     SUSDT-1.0-4h     SUSDT-1.0-6h
SUSDT-0.9-1h     SUSDT-0.9-2h     SUSDT-0.9-3h     SUSDT-0.9-4h     SUSDT-0.9-6h
```

The lowercase `-Nh` suffix (vs. the spread-width cohort's bare `-0.9` or
`-1.0-FRESH`) exists to keep this cohort's keys unambiguous even where a
width value is reused: `MINAUSDT-0.9-1h` and `MINAUSDT-0.9` (the
spread-width cohort's 0.9% instance) are visibly different keys, never
colliding, and neither collides with the live `MINAUSDT` bare key. All three
namespaces (`SYMBOL`, `SYMBOL-WIDTH`, `SYMBOL-WIDTH-Nh`) coexist in the same
`state["pairs"]` dict, per the same convention the spread-width cohort
established.

## Mechanics / implementation notes

- `src/paper_trade.py`: `process_pair_bars()` gained an optional
  `max_hold_bars` parameter (default = the existing global `MAX_HOLD_BARS`,
  so the 7 live pairs' and spread-width cohort's call sites are unchanged
  and their behavior is provably identical to before). This cohort's
  instances pass both `spread_pct` and `max_hold_bars` explicitly.
- To avoid 70 redundant hourly API calls, klines are fetched **once per
  underlying symbol** (7 fetches) and fanned out to that symbol's 10
  hold x width variants, each of which still has its own fully independent
  `pending_bid`/`pending_ask`/`totals`/`start_date_utc` state — no shared
  mutable state between variants beyond the read-only bar data itself. This
  cohort is processed by its own function (`cmd_run_hold_spread_cohort`),
  deliberately not sharing code with the original 7-pair loop or with the
  spread-width cohort's loop, so none of the three could be broken by a
  change intended for another.
- One hourly run now issues 21 kline fetches total: 7 for the live pairs, 7
  (shared) for the 42-instance spread-width cohort, 7 (shared) for this
  70-instance cohort — 126 instances processed, ~21s wall time, well inside
  the hourly cron window.
- Verified end-to-end before deployment, same practice as the spread-width
  cohort build:
  - `--dry-run` full run (126 total instances, 21 API fetches, ~11.4s) with
    zero writes — `sha256sum` of `data/paper_trade_state.json` and
    `data/paper_trade_events.csv` identical before and after.
  - A live run then seeded all 70 new instances (`start_date_utc` =
    `2026-08-23T11:28:36Z` for all 70) while a before/after diff of the full
    state file confirmed: all 51 pre-existing `pairs` entries (7 live pairs
    + 42 spread-width cohort instances + the leftover rejected-candidate
    `ETHWUSDT` entry) byte-identical; exactly 70 new keys added, matching
    `HOLD_SPREAD_INSTRUMENTS` precisely; `params` (notional, fee schedule)
    unchanged; events CSV grew by zero rows (seeding a fresh instance emits
    no events, same as documented for the spread-width cohort's launch).
  - A follow-up `--dry-run` confirmed idempotency: state hash after the seed
    run stayed fixed under a further dry pass.
- New CLI: `python src/paper_trade.py --status-hold-spread` (read-only,
  grouped by hold then width) and `--suspend`/`--resume` now also accept
  this cohort's instance IDs (e.g. `--suspend PIPPINUSDT-0.9-1h`).
  `--suspend`/`--resume` previously force-uppercased their argument, which
  would have silently mismatched this cohort's lowercase `-Nh` suffix
  (`...-1h` → `...-1H`); fixed to resolve case-insensitively (exact match
  first, then upper-case fallback for the older all-uppercase instance IDs),
  verified with `MINAUSDT-0.9-6h`, `minausdt`, and `MINAUSDT-0.9` all
  resolving correctly in a dry-run.
- Runs on the existing hourly cron entry — no new cron job added; one run
  now processes all 126 instances.

## Risk carry-forwards

- **PIPPIN**, already flagged in the spread-width cohort for forced-close
  severity worsening at narrower spreads, shows the same pattern on the hold
  axis in this backtest sweep (-0.35% mean forced-net at 1h vs. -1.44% at
  6h) — the steepest severity degradation of any of the 7 pairs on either
  axis tested so far.
- **XPR and SFP are the exceptions** where forced-close severity does not
  worsen with longer holds in the backtest sweep (XPR's forced-close mean
  net is positive throughout; SFP improves at the 6h endpoint, though on a
  small n=13 sample). Worth watching whether that holds forward or is itself
  a single-window artifact — precisely the kind of thing this cohort exists
  to check.

## Decision framework

This cohort is diagnostic. No live pair's `MAX_HOLD_BARS` or `SPREAD_PCT`
changes based on this backtest sweep or on early cohort results — same
explicit instruction carried over from the spread-width cohort.

**Planned re-check window: 2026-09-12 to 2026-09-22 (roughly 20–30 days
from 2026-08-23).** At that point, per hold/width cell and per pair, check:

- Fill-adjusted monthly net (or simple realized P&L over the window, since
  all 70 share a start date and can be compared directly without
  annualizing)
- Complete-RT count vs. forced-close count (fill/forced-close frequency) per
  hold window — does the backtest's rate reduction at longer holds
  replicate forward?
- Mean net per forced close, per hold window, per pair — specifically
  whether the 5/7-pairs severity-worsens-with-longer-holds pattern found in
  the backtest replicates with real forward fills, or was a single-window
  artifact (as XYO's narrow-spread gain turned out to be in the spread-width
  cohort's motivating backtest)
- Whether the 1.0%/3h cell (this cohort's replica of the live pairs' current
  params, but on a fresh same-day clock) tracks the original live pairs
  closely — a divergence would indicate a time-period effect distinct from
  anything attributable to hold window or spread width
- Cross-reference against the spread-width cohort's own re-check (planned
  2026-09-15 to 2026-09-21) where the two cohorts' 3h/1.0% and 3h/0.9%
  cells overlap in design intent, as a partial forward-data cross-check
  between the two studies

Only after that check — with real forward fill data, not another replay of
the same ~20-day backtest window — should any live `MAX_HOLD_BARS` or
`SPREAD_PCT` change be considered.
