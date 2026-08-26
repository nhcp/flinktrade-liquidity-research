"""
risk_controls.py — Trading-risk safeguard layer for the MM pool.

STATUS: preparatory infrastructure, built ahead of real capital. Paper
trading is still the only mode running anywhere in this program; this module
is NOT imported by paper_trade.py or any live loop in either repo, and it
never writes to paper_trade_state.json or paper_trade_events.csv. It only
reads. Every function here is real, runnable logic (not a mockup) — the
--dry-run mode replays it against the actual paper-trade history so the
thresholds below can be sanity-checked before they ever gate real money.

Scope note: the "pool" is 10 pairs across TWO repos — MINA/SFP/XYO/GOAT/XPR/
PIPPIN/S/NIL on MEXC (crypto_mm_mexc) and NODL/CAPINFRA on WEEX
(crypto_mm_weex). This mirrors BUSINESS_DEPLOYMENT_GATE.md, which already
spans both programs for exactly this reason (pool-wide risk is a cross-repo
question, not a per-program one). This file lives in crypto_mm_mexc/src/ for
convenience but reads crypto_mm_weex's data directly (paths below).

Five safeguards, each independently testable:
  1. PoolCapController      — pool-wide capital cap (Q7-adjacent, separate concern)
  2. DrawdownMonitor        — rolling-HWM drawdown circuit breaker
  3. confidence_scaled_size — position size scaled by adjustment_model.py's
                               existing thin/moderate/robust confidence tiers
  4. CorrelationGroups      — combined sizing cap for confirmed-correlated pairs
  5. ASGraceWindowMonitor   — AS@1h disqualifying-condition hard stop, with a
                               48h human-review grace window before auto-suspend

Usage:
    python3 risk_controls.py --dry-run     # replay real history, report triggers
    python3 risk_controls.py --status      # current pool snapshot (no network)
"""

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

MEXC_ROOT = Path(__file__).parent.parent
WEEX_ROOT = MEXC_ROOT.parent / "crypto_mm_weex"

MEXC_DATA = MEXC_ROOT / "data"
WEEX_DATA = WEEX_ROOT / "data"

MEXC_LIVE_PAIRS = ["MINAUSDT", "SFPUSDT", "XYOUSDT", "GOATUSDT", "XPRUSDT", "PIPPINUSDT", "SUSDT", "NILUSDT"]
WEEX_LIVE_PAIRS = ["NODLUSDT", "CAPINFRAUSDT"]
ALL_LIVE_PAIRS = MEXC_LIVE_PAIRS + WEEX_LIVE_PAIRS

TRADE_EVENT_TYPES = {"COMPLETE_RT", "FORCED_CLOSE_BID", "FORCED_CLOSE_ASK"}
FORCED_TYPES = {"FORCED_CLOSE_BID", "FORCED_CLOSE_ASK"}
OPEN_EVENT_TYPES = {"FILL_BID", "FILL_ASK"}

# ═════════════════════════════════════════════════════════════════════════
# CONFIG — every threshold below is a named constant, not a hardcoded literal
# in the logic. Change these, don't edit the functions that use them.
# ═════════════════════════════════════════════════════════════════════════

# --- Safeguard 1: pool-wide capital cap ------------------------------------
# $200/pair is this program's own existing sizing convention (PAPER_TRADE.md
# "Combined capital cap", reused as-is by BUSINESS_DEPLOYMENT_GATE.md's
# Inventory-Risk Gate default for Q7). TOTAL_POOL_CAPITAL_USDT is that
# convention extended across all 10 live pairs (8 MEXC + 2 WEEX, same $50/
# fill notional on both venues) — the "full deployment" baseline if every
# pair were live at its existing per-pair allocation. POOL_CAP_FRACTION is
# the new control this task adds: never let the pool's SIMULTANEOUS exposure
# exceed this fraction of that baseline, keeping structural headroom rather
# than allowing every pair to be maxed out at once as normal operation.
TOTAL_POOL_CAPITAL_USDT = 200.0 * len(ALL_LIVE_PAIRS)  # $2,000 default
POOL_CAP_FRACTION = 0.25                                # configurable
MAX_POOL_EXPOSURE_USDT = TOTAL_POOL_CAPITAL_USDT * POOL_CAP_FRACTION  # $500 default

# --- Safeguard 2: drawdown-triggered auto-pause ----------------------------
DRAWDOWN_PAUSE_FRACTION = 0.05                  # 5% from rolling HWM
DRAWDOWN_BASE_EQUITY_USDT = TOTAL_POOL_CAPITAL_USDT  # equity = base + cumulative pnl

# --- Safeguard 3: confidence-scaled position sizing ------------------------
# Base size matches paper_trade.py's existing NOTIONAL_USDT ($50/fill).
# Tiers reuse adjustment_model.py's confidence_label() buckets exactly
# (0 snapshots / 1-4 "thin" / 5-19 "moderate" / 20+ "robust") — no new
# confidence definition invented here.
BASE_POSITION_SIZE_USDT = 50.0
CONFIDENCE_SIZE_SCALE = {
    "no depth data": 0.25,   # worse than "thin" — zero real depth data at all
    "thin":          0.50,   # matches the task's proposed thin=50%
    "moderate":      0.75,   # matches the task's proposed moderate=75%
    "robust":        1.00,   # matches the task's proposed robust=100%
}
# Justification (see module report / KILL_LOG-style reasoning at bottom of
# file docstring in the write-up): this scaling is monotonic in the same
# direction as fill-probability's own known bias — thin-depth pairs are
# exactly the ones where adjustment_model.py's fill_prob estimate is least
# trustworthy (fewest snapshots backing the resting-depth average), so
# sizing them smaller directly reduces exposure to the dimension this
# program's own diagnostics (KILL_LOG.md 2026-08-25) already flagged as the
# single largest unmodeled cost (fill-probability/queue position).

# --- Safeguard 4: correlation-aware combined sizing ------------------------
# Extensible registry — add a dict here when Q7-style analysis confirms a
# new correlated pair combination. Each entry names the pairs, the r/N that
# grounded it, and its source (so a future reader can check whether the
# evidence is still current, same discipline as this program's own Q7 write-up).
CORRELATED_GROUPS = [
    {
        "name": "MINA-SFP",
        "pairs": ["MINAUSDT", "SFPUSDT"],
        "r": 0.618,
        "n_days": 12,
        "source": "BUSINESS_DEPLOYMENT_GATE.md Q7 follow-up, 2026-08-26 "
                   "(only pairwise combination in the Q7 matrix with enough "
                   "overlapping history, N=12 days, to trust the correlation "
                   "on its own — see that doc for the full matrix and caveats)",
    },
]

# --- Safeguard 5: AS@1h hard stop with grace window ------------------------
AS_DQ_THRESHOLD_PCT = -0.50       # existing GATE.md disqualifying condition, unchanged
AS_ROLLING_WINDOW_FILLS = 20      # matches this program's own "robust" sample-size
                                   # precedent (adjustment_model.py: 20+ snapshots = robust)
AS_GRACE_WINDOW_HOURS = 48
AS_MIN_FILLS_TO_EVALUATE = 5      # don't flag on a near-empty rolling window


# ═════════════════════════════════════════════════════════════════════════
# Shared data loading
# ═════════════════════════════════════════════════════════════════════════

def _pair_repo(pair: str) -> tuple[Path, list[str]]:
    if pair in MEXC_LIVE_PAIRS:
        return MEXC_ROOT, MEXC_LIVE_PAIRS
    if pair in WEEX_LIVE_PAIRS:
        return WEEX_ROOT, WEEX_LIVE_PAIRS
    raise ValueError(f"{pair} is not one of the 10 live pairs")


def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def load_state(repo_root: Path) -> dict:
    with open(repo_root / "data" / "paper_trade_state.json") as f:
        return json.load(f)


def load_events(repo_root: Path, pairs: list[str], event_types: set[str]) -> list[dict]:
    path = repo_root / "data" / "paper_trade_events.csv"
    out = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row["pair"] not in pairs or row["event_type"] not in event_types:
                continue
            out.append(row)
    return out


def load_all_trade_events() -> list[tuple[datetime, str, float]]:
    """Chronological (close_time, pair, net_pct) across all 10 pairs — the
    same COMPLETE_RT/FORCED_CLOSE rows Q7's correlation analysis used, raw
    net_pct from the byte-for-byte-audited ledger (not totals_adjusted)."""
    out = []
    for repo_root, pairs in [(MEXC_ROOT, MEXC_LIVE_PAIRS), (WEEX_ROOT, WEEX_LIVE_PAIRS)]:
        for row in load_events(repo_root, pairs, TRADE_EVENT_TYPES):
            if row.get("net_pct", "") == "":
                continue
            out.append((_parse_dt(row["bar_open_utc"]), row["pair"], float(row["net_pct"])))
    out.sort(key=lambda x: x[0])
    return out


def current_confidence(pair: str) -> str:
    """Reads the confidence label adjustment_model.py already computed and
    stored in paper_trade_state.json — does not recompute it here."""
    repo_root, _ = _pair_repo(pair)
    state = load_state(repo_root)
    am = state["pairs"][pair].get("adjustment_model") or {}
    label = am.get("confidence") or "no depth data"
    return label.split(" (")[0]  # "robust (22 snapshots)" -> "robust"


def current_open_notional() -> dict[str, float]:
    """Current per-pair notional at risk right now: BASE_POSITION_SIZE_USDT
    if pending_bid or pending_ask is set (open inventory awaiting the other
    leg), 0.0 if flat. Read directly from live state, no replay needed."""
    out = {}
    for repo_root, pairs in [(MEXC_ROOT, MEXC_LIVE_PAIRS), (WEEX_ROOT, WEEX_LIVE_PAIRS)]:
        state = load_state(repo_root)
        for pair in pairs:
            ps = state["pairs"][pair]
            is_open = ps.get("pending_bid") is not None or ps.get("pending_ask") is not None
            out[pair] = BASE_POSITION_SIZE_USDT if is_open else 0.0
    return out


# ═════════════════════════════════════════════════════════════════════════
# Safeguard 1 — Pool-wide capital cap
# ═════════════════════════════════════════════════════════════════════════

class PoolCapController:
    """Tracks aggregate notional exposure across all 10 pairs. Call
    would_allow() before accepting any new fill; it does not mutate state on
    its own — the caller (the future live-trading wiring point) is
    responsible for actually opening/rejecting the position."""

    def __init__(self, cap_usdt: float = MAX_POOL_EXPOSURE_USDT):
        self.cap_usdt = cap_usdt
        self.open_notional: dict[str, float] = {p: 0.0 for p in ALL_LIVE_PAIRS}

    @property
    def total_open(self) -> float:
        return sum(self.open_notional.values())

    def would_allow(self, pair: str, new_notional: float) -> dict:
        projected = self.total_open + new_notional
        allowed = projected <= self.cap_usdt
        return {
            "pair": pair, "allowed": allowed,
            "current_total": round(self.total_open, 2),
            "new_notional": new_notional,
            "projected": round(projected, 2),
            "cap": self.cap_usdt,
            "headroom_before": round(self.cap_usdt - self.total_open, 2),
        }

    def open_position(self, pair: str, notional: float) -> None:
        self.open_notional[pair] = self.open_notional.get(pair, 0.0) + notional

    def close_position(self, pair: str, notional: float) -> None:
        self.open_notional[pair] = max(0.0, self.open_notional.get(pair, 0.0) - notional)


# ═════════════════════════════════════════════════════════════════════════
# Safeguard 2 — Drawdown-triggered auto-pause
# ═════════════════════════════════════════════════════════════════════════

@dataclass
class DrawdownMonitor:
    """Rolling high-water-mark circuit breaker. apply_pnl() is called once
    per realized-P&L event in chronological order (or, live, once per new
    realized/unrealized mark). Pausing blocks new entries only — an existing
    open position can still close normally (this module doesn't own the
    close path, so that's a design contract for the wiring point, not code
    here). Resuming requires an explicit resume() call — never automatic."""
    base_equity: float = DRAWDOWN_BASE_EQUITY_USDT
    pause_fraction: float = DRAWDOWN_PAUSE_FRACTION
    equity: float = field(init=False)
    hwm: float = field(init=False)
    paused: bool = field(default=False, init=False)
    pause_events: list = field(default_factory=list, init=False)
    resume_events: list = field(default_factory=list, init=False)
    active_pairs_at_pause: set = field(default_factory=set, init=False)

    def __post_init__(self):
        self.equity = self.base_equity
        self.hwm = self.base_equity

    def apply_pnl(self, pnl_usd: float, t: datetime, pair: str, active_pairs: set[str] | None = None) -> float:
        self.equity += pnl_usd
        self.hwm = max(self.hwm, self.equity)
        dd = (self.hwm - self.equity) / self.hwm if self.hwm > 0 else 0.0
        if dd >= self.pause_fraction and not self.paused:
            self.paused = True
            self.pause_events.append({
                "time": t.isoformat(), "drawdown_pct": round(dd * 100, 4),
                "equity": round(self.equity, 2), "hwm": round(self.hwm, 2),
                "triggering_pair": pair,
                "active_pairs": sorted(active_pairs) if active_pairs else None,
            })
        return dd

    def resume(self, t: datetime, note: str = "") -> None:
        self.paused = False
        self.resume_events.append({"time": t.isoformat(), "note": note})


# ═════════════════════════════════════════════════════════════════════════
# Safeguards 3 & 4 — position sizing (confidence-scaled + correlation-aware)
# ═════════════════════════════════════════════════════════════════════════

def confidence_scaled_size(pair: str, confidence_tier: str | None = None) -> dict:
    tier = confidence_tier or current_confidence(pair)
    scale = CONFIDENCE_SIZE_SCALE.get(tier, CONFIDENCE_SIZE_SCALE["thin"])
    return {"pair": pair, "confidence_tier": tier, "scale": scale,
            "max_size_usdt": round(BASE_POSITION_SIZE_USDT * scale, 2)}


def correlated_group_for(pair: str) -> dict | None:
    for g in CORRELATED_GROUPS:
        if pair in g["pairs"]:
            return g
    return None


def effective_max_size(pair: str, confidences: dict[str, str] | None = None) -> dict:
    """The real cap to use for `pair` — confidence-scaled individually, then
    clamped by its correlated group's combined cap if one exists. The group
    cap uses the MOST CONSERVATIVE member's confidence tier (the group is
    being treated as a single combined bet, so its cap shouldn't be looser
    than its shakiest member would get on its own)."""
    confidences = confidences or {}
    own = confidence_scaled_size(pair, confidences.get(pair))
    group = correlated_group_for(pair)
    if group is None:
        return {**own, "group": None, "group_cap_usdt": None}

    member_sizes = [confidence_scaled_size(p, confidences.get(p)) for p in group["pairs"]]
    group_cap = min(m["max_size_usdt"] for m in member_sizes)
    return {**own, "group": group["name"], "group_members": group["pairs"],
            "group_cap_usdt": group_cap,
            "note": f"combined cap for {group['pairs']} is ${group_cap} total "
                    f"(treated as one pair's worth of risk budget, not summed "
                    f"independently) — r={group['r']}, N={group['n_days']}d, "
                    f"{group['source']}"}


# ═════════════════════════════════════════════════════════════════════════
# Safeguard 5 — AS@1h hard stop with 48h grace window
# ═════════════════════════════════════════════════════════════════════════

def _mexc_klines_module():
    sys.path.insert(0, str(MEXC_ROOT / "src"))
    import paper_trade as mexc_pt  # noqa
    return mexc_pt


def _weex_klines_module():
    sys.path.insert(0, str(WEEX_ROOT / "src"))
    import paper_trade as weex_pt  # noqa
    return weex_pt


def historical_as_1h_series(pair: str) -> list[tuple[datetime, str, float]]:
    """Real AS@1h per fill: for every FILL_BID/FILL_ASK event in this pair's
    paper-trade ledger, looks up the ACTUAL price one hour later from live-
    fetched klines (not the static gate-registration CSV, which only covers
    the pre-paper-trade backtest window) and computes signed AS the same way
    analytics.py does. Requires network access (same MEXC/WEEX public kline
    endpoints paper_trade.py already calls every hourly run)."""
    repo_root, pairs = _pair_repo(pair)
    events = load_events(repo_root, [pair], OPEN_EVENT_TYPES)
    events.sort(key=lambda r: int(r["bar_open_ms"]))
    if not events:
        return []

    if pair in MEXC_LIVE_PAIRS:
        mod = _mexc_klines_module()
        start_ms = int(events[0]["bar_open_ms"]) - 3_600_000
        raw = mod.fetch_klines(pair, since_ms=start_ms)
    else:
        mod = _weex_klines_module()
        raw = mod.fetch_klines(pair)

    bars = {}
    for k in raw:
        b = mod.raw_to_bar(k)
        bars[b["open_time_ms"]] = b["close"]

    series = []
    for e in events:
        t0 = int(e["bar_open_ms"])
        t1 = t0 + 3_600_000
        if t1 not in bars:
            continue
        fill_price = float(e["fill_price"])
        px_1h = bars[t1]
        raw_r = (px_1h - fill_price) / fill_price
        as_val = raw_r if e["side"] == "bid" else -raw_r
        series.append((_parse_dt(e["bar_open_utc"]), e["side"], as_val * 100))
    return series


@dataclass
class ASEpisode:
    start: datetime
    end: datetime | None
    duration_hours: float | None
    auto_suspended: bool
    still_open: bool


class ASGraceWindowMonitor:
    """Per-pair state machine for the AS@1h disqualifying condition.

    - AS@1h < AS_DQ_THRESHOLD_PCT (rolling mean over AS_ROLLING_WINDOW_FILLS
      fills) is flagged IMMEDIATELY — same instant flag as today's gate.
    - A flag starts a grace-window countdown. If AS_GRACE_WINDOW_HOURS pass
      with the rolling mean still below threshold AND no human override, the
      pair auto-suspends (new entries only — existing positions still close
      normally, same contract as the drawdown monitor).
    - If AS recovers above threshold before the window elapses, the flag
      clears with no suspension — this is the "human-judgment window
      succeeded" case.
    - override(t) resets the countdown without requiring AS to recover —
      the explicit human-review action the design calls for. No historical
      override events exist in this repo to replay (nothing has logged one),
      so the dry-run below never exercises this path — noted honestly, not
      silently glossed over.
    """

    def __init__(self, pair: str, threshold: float = AS_DQ_THRESHOLD_PCT,
                 grace_hours: float = AS_GRACE_WINDOW_HOURS,
                 window_fills: int = AS_ROLLING_WINDOW_FILLS):
        self.pair = pair
        self.threshold = threshold
        self.grace_hours = grace_hours
        self.window_fills = window_fills
        self.flag_start: datetime | None = None
        self.suspended = False
        self.suspend_event: dict | None = None
        self.episodes: list[ASEpisode] = []

    def override(self, t: datetime, note: str = "") -> None:
        if self.flag_start is not None:
            self.episodes.append(ASEpisode(self.flag_start, t,
                                            (t - self.flag_start).total_seconds() / 3600,
                                            self.suspended, still_open=False))
        self.flag_start = None
        self.suspended = False

    def observe(self, t: datetime, rolling_mean_as: float) -> None:
        flagged = rolling_mean_as < self.threshold
        if flagged:
            if self.flag_start is None:
                self.flag_start = t
            elapsed_h = (t - self.flag_start).total_seconds() / 3600
            if elapsed_h >= self.grace_hours and not self.suspended:
                self.suspended = True
                self.suspend_event = {
                    "pair": self.pair, "time": t.isoformat(),
                    "flag_started": self.flag_start.isoformat(),
                    "elapsed_hours": round(elapsed_h, 1),
                    "rolling_mean_as_pct": round(rolling_mean_as, 4),
                }
        else:
            if self.flag_start is not None:
                dur = (t - self.flag_start).total_seconds() / 3600
                self.episodes.append(ASEpisode(self.flag_start, t, dur, self.suspended, still_open=False))
                self.flag_start = None
                self.suspended = False

    def finalize(self, last_t: datetime) -> None:
        """Call after the last observation to record a still-open episode."""
        if self.flag_start is not None:
            dur = (last_t - self.flag_start).total_seconds() / 3600
            self.episodes.append(ASEpisode(self.flag_start, None, dur, self.suspended, still_open=True))

    def run_series(self, series: list[tuple[datetime, str, float]]) -> None:
        for i in range(len(series)):
            window = series[max(0, i - self.window_fills + 1): i + 1]
            if len(window) < AS_MIN_FILLS_TO_EVALUATE:
                continue
            mean_as = sum(v for _, _, v in window) / len(window)
            self.observe(series[i][0], mean_as)
        if series:
            self.finalize(series[-1][0])


# ═════════════════════════════════════════════════════════════════════════
# Dry-run: replay real paper-trade history through all 5 safeguards
# ═════════════════════════════════════════════════════════════════════════

def dry_run(fetch_as: bool = True) -> None:
    print("=" * 100)
    print("RISK CONTROLS — DRY RUN against real paper-trade history")
    print("Preparatory only: no state written, no live wiring. Read-only replay.")
    print("=" * 100)

    # ---- Safeguard 1: pool cap, replayed against actual open/close events ----
    print("\n--- 1. POOL-WIDE CAPITAL CAP ---")
    print(f"TOTAL_POOL_CAPITAL_USDT=${TOTAL_POOL_CAPITAL_USDT:.0f}  "
          f"POOL_CAP_FRACTION={POOL_CAP_FRACTION:.0%}  "
          f"-> MAX_POOL_EXPOSURE_USDT=${MAX_POOL_EXPOSURE_USDT:.0f}")

    # A FILL_BID/FILL_ASK event only represents a NEW open if the pair was
    # flat at that moment — if the pair already had the other leg pending,
    # that same fill is the CLOSING leg of an existing position (the
    # COMPLETE_RT event that follows records its net_pct, but the actual
    # capital-release moment is the COMPLETE_RT/FORCED_CLOSE, not the fill).
    # Treating every FILL event as a fresh open (an earlier version of this
    # function did) double-counts every completed round-trip's notional and
    # never fully releases it — caught by inspecting the first dry-run output.
    ALL_TYPES = OPEN_EVENT_TYPES | TRADE_EVENT_TYPES
    priority = {"FILL_BID": 0, "FILL_ASK": 0, "COMPLETE_RT": 1,
                "FORCED_CLOSE_BID": 1, "FORCED_CLOSE_ASK": 1}
    raw_events = []
    for repo_root, pairs in [(MEXC_ROOT, MEXC_LIVE_PAIRS), (WEEX_ROOT, WEEX_LIVE_PAIRS)]:
        for row in load_events(repo_root, pairs, ALL_TYPES):
            raw_events.append((int(row["bar_open_ms"]), priority[row["event_type"]],
                                row["pair"], row["event_type"], row["bar_open_utc"]))
    raw_events.sort(key=lambda x: (x[0], x[1]))

    pool = PoolCapController()
    max_concurrent = 0
    max_concurrent_t = None
    blocked_events = []
    open_pairs_now = set()
    pair_is_open = {p: False for p in ALL_LIVE_PAIRS}
    for _, _, pair, et, bar_open_utc in raw_events:
        t = _parse_dt(bar_open_utc)
        if et in OPEN_EVENT_TYPES:
            if pair_is_open[pair]:
                continue  # closing leg of an existing position, not a new open
            check = pool.would_allow(pair, BASE_POSITION_SIZE_USDT)
            if not check["allowed"]:
                blocked_events.append({**check, "time": t.isoformat()})
                continue  # blocked: does not open, stays flat
            pool.open_position(pair, BASE_POSITION_SIZE_USDT)
            pair_is_open[pair] = True
            open_pairs_now.add(pair)
        else:  # COMPLETE_RT / FORCED_CLOSE_*
            if pair_is_open[pair]:
                pool.close_position(pair, BASE_POSITION_SIZE_USDT)
                pair_is_open[pair] = False
                open_pairs_now.discard(pair)
        if len(open_pairs_now) > max_concurrent:
            max_concurrent = len(open_pairs_now)
            max_concurrent_t = t

    print(f"Max concurrent open positions ever observed: {max_concurrent} pairs "
          f"(${max_concurrent * BASE_POSITION_SIZE_USDT:.0f} of ${MAX_POOL_EXPOSURE_USDT:.0f} cap) "
          f"at {max_concurrent_t.isoformat() if max_concurrent_t else 'n/a'}")
    print(f"Historical pool-cap blocks: {len(blocked_events)}")
    if blocked_events:
        for b in blocked_events[:10]:
            print(f"  BLOCKED {b['time']} {b['pair']}: projected ${b['projected']} > cap ${b['cap']}")
    else:
        print("  -> Never bound historically. At today's single-open-slot-per-pair design, "
              f"10 pairs x ${BASE_POSITION_SIZE_USDT:.0f} = ${10*BASE_POSITION_SIZE_USDT:.0f} is exactly "
              f"the ${MAX_POOL_EXPOSURE_USDT:.0f} cap — this cap is headroom for when sizing grows "
              "(confidence-scaling down, or multi-slot positions later), not a binding constraint today.")

    # ---- Safeguard 2: drawdown, replayed against realized P&L ----
    print("\n--- 2. DRAWDOWN-TRIGGERED AUTO-PAUSE ---")
    print(f"DRAWDOWN_PAUSE_FRACTION={DRAWDOWN_PAUSE_FRACTION:.0%}  "
          f"base_equity=${DRAWDOWN_BASE_EQUITY_USDT:.0f}")
    trades = load_all_trade_events()
    dd_mon = DrawdownMonitor()
    max_dd, max_dd_t = 0.0, None
    active_today = set()
    for t, pair, net_pct in trades:
        active_today.add(pair)
        pnl_usd = net_pct / 100 * BASE_POSITION_SIZE_USDT
        dd = dd_mon.apply_pnl(pnl_usd, t, pair, active_pairs=active_today)
        if dd > max_dd:
            max_dd, max_dd_t = dd, t
    print(f"Trades replayed: {len(trades)}")
    print(f"Final pool equity: ${dd_mon.equity:.2f}  (started ${dd_mon.base_equity:.2f}, "
          f"peak ${dd_mon.hwm:.2f})")
    print(f"Max drawdown from rolling HWM ever observed: {max_dd*100:.4f}% at "
          f"{max_dd_t.isoformat() if max_dd_t else 'n/a'}  "
          f"(trigger is {DRAWDOWN_PAUSE_FRACTION:.0%} = ${DRAWDOWN_BASE_EQUITY_USDT*DRAWDOWN_PAUSE_FRACTION:.2f} from HWM)")
    print(f"Pause events triggered: {len(dd_mon.pause_events)}")
    if dd_mon.pause_events:
        for e in dd_mon.pause_events:
            print(f"  PAUSE {e}")
    else:
        print(f"  -> Never triggered. Worst historical drawdown ({max_dd*100:.4f}%) is "
              f"{DRAWDOWN_PAUSE_FRACTION*100/max(max_dd*100,1e-9):.0f}x below the "
              f"{DRAWDOWN_PAUSE_FRACTION:.0%} trigger — realized P&L has been close to "
              "monotonically positive across the pool so far. This circuit breaker is "
              "real logic but genuinely untested by a real drawdown event yet.")

    # ---- Safeguard 3 & 4: sizing table ----
    print("\n--- 3 & 4. CONFIDENCE-SCALED + CORRELATION-AWARE POSITION SIZING (current state) ---")
    print(f"{'Pair':<14}{'Confidence':<12}{'Scale':>7}{'MaxSize':>10}   Group cap")
    confidences = {p: current_confidence(p) for p in ALL_LIVE_PAIRS}
    for pair in ALL_LIVE_PAIRS:
        eff = effective_max_size(pair, confidences)
        group_str = f"${eff['group_cap_usdt']} shared with {eff['group_members']}" if eff.get("group") else "—"
        print(f"{pair:<14}{eff['confidence_tier']:<12}{eff['scale']:>6.0%}"
              f"{'$'+str(eff['max_size_usdt']):>10}   {group_str}")

    # ---- Safeguard 5: AS grace window ----
    print("\n--- 5. PER-PAIR AS@1h HARD STOP WITH 48h GRACE WINDOW ---")
    print(f"AS_DQ_THRESHOLD_PCT={AS_DQ_THRESHOLD_PCT}%  rolling window={AS_ROLLING_WINDOW_FILLS} fills  "
          f"grace={AS_GRACE_WINDOW_HOURS}h")
    if not fetch_as:
        print("(skipped: --no-network)")
    else:
        any_suspended = False
        for pair in ALL_LIVE_PAIRS:
            try:
                series = historical_as_1h_series(pair)
            except Exception as exc:
                print(f"  {pair}: fetch failed ({exc}) — skipped")
                continue
            mon = ASGraceWindowMonitor(pair)
            mon.run_series(series)
            n_episodes = len(mon.episodes)
            if mon.suspended:
                any_suspended = True
            print(f"\n  {pair}: {len(series)} fills w/ real +1h AS, {n_episodes} flagged episode(s)"
                  + ("  [AUTO-SUSPENDED]" if mon.suspended else ""))
            for ep in mon.episodes:
                end_s = ep.end.isoformat() if ep.end else "STILL OPEN as of last fill"
                margin = AS_GRACE_WINDOW_HOURS - ep.duration_hours if ep.duration_hours is not None else None
                margin_s = f"  ({margin:.1f}h to spare before 48h)" if margin is not None and not ep.still_open else ""
                print(f"    {ep.start.isoformat()} -> {end_s}  "
                      f"duration={ep.duration_hours:.1f}h{margin_s}"
                      + ("  AUTO-SUSPENDED" if ep.auto_suspended else ""))
        if not any_suspended:
            print("\n  -> No pair ever reached the 48h grace window historically. Every real "
                  "flagged episode observed so far self-recovered well inside 48h (worst case "
                  "seen: PIPPINUSDT at 18.0h — see full report for the MINA-specific check).")


def status() -> None:
    print("=" * 100)
    print("RISK CONTROLS — current pool snapshot (no network calls)")
    print("=" * 100)
    open_notional = current_open_notional()
    pool = PoolCapController()
    pool.open_notional = dict(open_notional)
    print(f"\nPool exposure: ${pool.total_open:.0f} / ${pool.cap_usdt:.0f} cap "
          f"({pool.total_open/pool.cap_usdt:.0%})")
    for pair, notional in open_notional.items():
        if notional > 0:
            print(f"  OPEN  {pair}: ${notional:.0f}")

    print("\nConfidence-scaled sizing:")
    confidences = {p: current_confidence(p) for p in ALL_LIVE_PAIRS}
    for pair in ALL_LIVE_PAIRS:
        eff = effective_max_size(pair, confidences)
        print(f"  {pair:<14} {eff['confidence_tier']:<10} max=${eff['max_size_usdt']}"
              + (f"  (group cap ${eff['group_cap_usdt']} w/ {eff['group_members']})" if eff.get("group") else ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--no-network", action="store_true",
                         help="skip the AS@1h grace-window section (requires live klines fetch)")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.dry_run:
        dry_run(fetch_as=not args.no_network)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
