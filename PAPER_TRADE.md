# Crypto MM MEXC — 30-Day Paper Trade
## Started: 2026-08-14  |  Target End: 2026-09-13

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
| Pairs             | MINA/USDT, KAVA/USDT |
| Spread            | 1.0% (0.5% each side from mid) |
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

Run `python src/paper_report.py` and verify:

| Metric | Warning level | Stop level |
|---|---|---|
| MINA bid-fill AS at t+1h | < -0.15% | < -0.50% (DQ) |
| Forced-close rate | > 80% | > 95% (gate DQ) |
| Mean net/forced close | < -0.10% | < -0.30% |

Log findings in the Results section below.

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

## Decision Framework After 30 Days

### Proceed to capital ($500 total, $200/pair, $50/fill) if:

- [ ] Both pairs: AS at t+1h > -0.15% × spread  (G4 maintained)
- [ ] Both pairs: AS at t+4h > -0.30% × spread  (G5 maintained)
- [ ] MINA: bid-fill AS at t+1h did NOT drop below -0.50% at any point
- [ ] Both pairs: forced-close rate < 95%
- [ ] Total realized P&L across 30 days: positive (any positive)

### Kill the thread if:

- MINA bid-fill AS at t+1h < -0.50% at any weekly check
- Both pairs: forced-close rate > 95% for 2 consecutive weeks
- KAVA: AS at t+1h < -0.50% (strong informed-flow signal)

### MINA-only kill (proceed with KAVA only):

- If MINA DQs but KAVA maintains all metrics
- Capital cap: $200 KAVA only, $50/fill
- Still counts as meaningful validation of the hypothesis

---

## Results (weekly append)

### Week 1 — 2026-08-14 to 2026-08-21

**2026-08-15:** KAVA/USDT suspended (`python3 src/paper_trade.py --suspend
KAVAUSDT`) on evidence from `liquidity_provision_v2/docs/FINAL_REPORT.md`
that its gate pass was a false positive — see "Status Update" at top of this
doc. MINA/USDT continues unaffected.

*Remaining weekly summary TBD — run `python src/paper_report.py` and paste here*

### Week 2 — 2026-08-21 to 2026-08-28

*TBD*

### Week 3 — 2026-08-28 to 2026-09-04

*TBD*

### Week 4 — 2026-09-04 to 2026-09-13

*TBD*

---

## Final Verdict (2026-09-13)

*TBD*
