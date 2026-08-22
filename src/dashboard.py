"""
Local dashboard for this repo's paper-trade state — read-only.

Loads data/paper_trade_state.json (never writes to it) and renders a single
self-contained HTML page:
  - "Live Research (MEXC)" — the 7 original live pairs, unchanged section,
    same data paper_report.py already tracks for them.
  - "Spread-Width Cohort" — the 42-instance forward test, grouped into 6
    collapsed-by-default sections (one per width). PIPPIN's row in every
    section carries a visible risk flag (see docs/SPREAD_WIDTH_COHORT_2026-08-22.md).

This is a local artifact generated from this repo's own state — it does not
read from, write to, or deploy to any other service.

Usage:
    python src/dashboard.py                  # writes docs/dashboard.html
    python src/dashboard.py --out FILE.html
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paper_trade import (  # noqa: E402
    STATE_FILE, PAIRS as LIVE_PAIRS_ALL, COHORT_BASE_PAIRS, COHORT_WIDTH_GROUPS,
    COHORT_FRESH_CONTROL_WIDTH, COHORT_NOTES, cohort_instance_id,
)

LIVE_PAIRS = [p for p in LIVE_PAIRS_ALL if p != "KAVAUSDT"]   # currently-live 7
SUSPENDED_PAIRS = ["KAVAUSDT"]


def _elapsed_days(start_utc: str | None) -> float:
    if not start_utc:
        return 0.0
    start = datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - start).total_seconds() / 86400


def _fmt_pct(v: float) -> str:
    return f"{'+' if v > 0 else ''}{v:.4f}%"


def load_state() -> dict:
    with open(STATE_FILE) as f:
        return json.load(f)


def build_live_rows(state: dict) -> str:
    rows = []
    for pair in LIVE_PAIRS + SUSPENDED_PAIRS:
        ps = state["pairs"].get(pair)
        if not ps:
            continue
        t = ps["totals"]
        susp = ps.get("suspended", False)
        elapsed = _elapsed_days(ps.get("start_date_utc"))
        n_rt = t["complete_rts"] + t["forced_closes"]
        fc_rate = (t["forced_closes"] / n_rt * 100) if n_rt else 0.0
        row_cls = "row-suspended" if susp else ""
        badge = '<span class="chip chip-muted">suspended</span>' if susp else ""
        pnl_cls = "pos" if t["realized_pnl_pct_sum"] >= 0 else "neg"
        start_date = (ps.get("start_date_utc") or "—")[:10]
        rows.append(f"""<tr class="{row_cls}">
          <td class="col-symbol"><span class="mono sym">{pair}</span>{badge}</td>
          <td class="mono num">{start_date}</td>
          <td class="mono num">{elapsed:.1f}d</td>
          <td class="mono num">{t['fills']}</td>
          <td class="mono num">{t['complete_rts']}</td>
          <td class="mono num">{t['forced_closes']}</td>
          <td class="mono num">{fc_rate:.1f}%</td>
          <td class="mono num {pnl_cls}">{_fmt_pct(t['realized_pnl_pct_sum'])}</td>
        </tr>""")
    return "".join(rows)


def build_cohort_table(state: dict, width: float) -> tuple[str, dict]:
    """Returns (rows_html, aggregate_dict) for one width group."""
    rows = []
    agg = {"fills": 0, "complete_rts": 0, "forced_closes": 0, "net": 0.0}
    for symbol in COHORT_BASE_PAIRS:
        iid = cohort_instance_id(symbol, width)
        ps = state["pairs"].get(iid, {})
        t = ps.get("totals", {"fills": 0, "complete_rts": 0, "forced_closes": 0, "realized_pnl_pct_sum": 0.0})
        agg["fills"] += t["fills"]
        agg["complete_rts"] += t["complete_rts"]
        agg["forced_closes"] += t["forced_closes"]
        agg["net"] += t["realized_pnl_pct_sum"]

        n_rt = t["complete_rts"] + t["forced_closes"]
        fc_rate = (t["forced_closes"] / n_rt * 100) if n_rt else 0.0
        elapsed = _elapsed_days(ps.get("start_date_utc"))
        pnl_cls = "pos" if t["realized_pnl_pct_sum"] >= 0 else "neg"
        is_pippin = symbol == "PIPPINUSDT"
        row_cls = "row-flagged" if is_pippin else ""
        flag_html = (f'<div class="risk-flag">⚠ {COHORT_NOTES[symbol]}</div>'
                     if is_pippin and symbol in COHORT_NOTES else "")
        rows.append(f"""<tr class="{row_cls}">
          <td class="col-symbol">
            <span class="mono sym">{iid}</span>
            {flag_html}
          </td>
          <td class="mono num">{elapsed:.1f}d</td>
          <td class="mono num">{t['fills']}</td>
          <td class="mono num">{t['complete_rts']}</td>
          <td class="mono num">{t['forced_closes']}</td>
          <td class="mono num">{fc_rate:.1f}%</td>
          <td class="mono num {pnl_cls}">{_fmt_pct(t['realized_pnl_pct_sum'])}</td>
        </tr>""")
    return "".join(rows), agg


def build_cohort_section(state: dict, width: float, open_first: bool) -> str:
    is_control = width == COHORT_FRESH_CONTROL_WIDTH
    label = "1.0% — fresh control" if is_control else f"{width:.1f}%"
    subtitle = ("Same width as the live pairs, new clock started today — isolates "
                "width effects from time-period effects." if is_control else
                "Narrower than the live 1.0% baseline.")
    rows_html, agg = build_cohort_table(state, width)
    open_attr = " open" if open_first else ""
    control_cls = " cohort-control" if is_control else ""

    return f"""
      <details class="cohort{control_cls}"{open_attr}>
        <summary>
          <div class="cohort-summary">
            <span class="width-badge">{label}</span>
            <span class="cohort-sub">{subtitle}</span>
            <span class="cohort-agg mono">
              {len(COHORT_BASE_PAIRS)} pairs · {agg['fills']} fills · {agg['complete_rts']} RT ·
              {agg['forced_closes']} forced ·
              <span class="{'pos' if agg['net'] >= 0 else 'neg'}">{_fmt_pct(agg['net'])}</span> combined
            </span>
            <span class="chevron" aria-hidden="true"></span>
          </div>
        </summary>
        <div class="cohort-body">
          <table>
            <thead>
              <tr>
                <th>Instance</th><th>Age</th><th>Fills</th><th>Complete</th>
                <th>Forced</th><th>FC rate</th><th>Realized net</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
      </details>"""


def render(state: dict) -> str:
    live_rows = build_live_rows(state)
    cohort_sections = "".join(
        build_cohort_section(state, w, open_first=False) for w in COHORT_WIDTH_GROUPS
    )
    total_cohort = len(COHORT_BASE_PAIRS) * len(COHORT_WIDTH_GROUPS)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    last_run = state.get("meta", {}).get("last_run_utc", "—")

    return f"""<title>S8 Spread Lab</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #F5F7FA;
    --surface: #FFFFFF;
    --surface-2: #EDF1F6;
    --line: #DCE3EA;
    --ink: #101521;
    --ink-2: #48515F;
    --ink-3: #828C9A;
    --accent: #0F6E67;
    --accent-ink: #FFFFFF;
    --good: #1E8E5A;
    --good-bg: #E6F4EC;
    --warn: #B8720F;
    --warn-bg: #FBF0DD;
    --risk: #C1352E;
    --risk-bg: #FBEAE8;
    --shadow: 0 1px 2px rgba(16,21,33,0.04), 0 8px 24px rgba(16,21,33,0.06);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #0E1218;
      --surface: #161C25;
      --surface-2: #1C2430;
      --line: #2A3441;
      --ink: #E7ECF2;
      --ink-2: #ADB7C4;
      --ink-3: #74808F;
      --accent: #45C7BB;
      --accent-ink: #06231F;
      --good: #52D591;
      --good-bg: #123324;
      --warn: #E3A93D;
      --warn-bg: #362A10;
      --risk: #F1786F;
      --risk-bg: #3A1917;
      --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.4);
    }}
  }}
  :root[data-theme="dark"] {{
    --bg: #0E1218;
    --surface: #161C25;
    --surface-2: #1C2430;
    --line: #2A3441;
    --ink: #E7ECF2;
    --ink-2: #ADB7C4;
    --ink-3: #74808F;
    --accent: #45C7BB;
    --accent-ink: #06231F;
    --good: #52D591;
    --good-bg: #123324;
    --warn: #E3A93D;
    --warn-bg: #362A10;
    --risk: #F1786F;
    --risk-bg: #3A1917;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.4);
  }}

  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--ink);
    font-family: "IBM Plex Sans", -apple-system, "Segoe UI", sans-serif;
    margin: 0;
    padding: 2.5rem 1.5rem 5rem;
    line-height: 1.5;
  }}
  .mono {{ font-family: "IBM Plex Mono", ui-monospace, monospace; font-variant-numeric: tabular-nums; }}
  .wrap {{ max-width: 920px; margin: 0 auto; }}

  header.masthead {{ margin-bottom: 2.25rem; }}
  .eyebrow {{
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.72rem;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 0 0 0.5rem;
  }}
  h1 {{
    font-family: "Fraunces", Georgia, serif;
    font-optical-sizing: auto;
    font-weight: 600;
    font-size: clamp(1.7rem, 3vw, 2.3rem);
    letter-spacing: -0.01em;
    text-wrap: balance;
    margin: 0 0 0.4rem;
    color: var(--ink);
  }}
  .masthead-sub {{ color: var(--ink-2); font-size: 0.98rem; max-width: 62ch; }}
  .meta-strip {{
    display: flex; flex-wrap: wrap; gap: 1.1rem 2rem;
    margin-top: 1.4rem; padding-top: 1.1rem; border-top: 1px solid var(--line);
    font-size: 0.82rem; color: var(--ink-3);
  }}
  .meta-strip b {{ color: var(--ink); font-weight: 600; }}

  section {{ margin-bottom: 2.4rem; }}
  h2 {{
    font-family: "Fraunces", Georgia, serif;
    font-weight: 500;
    font-size: 1.28rem;
    margin: 0 0 0.25rem;
    color: var(--ink);
  }}
  .section-sub {{ color: var(--ink-3); font-size: 0.86rem; margin: 0 0 1rem; max-width: 68ch; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 0.86rem; }}
  thead th {{
    text-align: right; font-weight: 600; font-size: 0.72rem;
    letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-3);
    padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--line);
  }}
  thead th:first-child, td.col-symbol {{ text-align: left; }}
  tbody td {{ padding: 0.55rem 0.6rem; border-bottom: 1px solid var(--line); }}
  tbody tr:last-child td {{ border-bottom: none; }}
  td.num {{ text-align: right; }}
  .sym {{ font-weight: 500; }}
  .pos {{ color: var(--good); }}
  .neg {{ color: var(--risk); }}

  .live-table-wrap {{
    background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
    box-shadow: var(--shadow); overflow-x: auto; padding: 0.3rem 1rem;
  }}
  tr.row-suspended {{ opacity: 0.5; }}
  .chip {{
    display: inline-block; font-size: 0.66rem; font-weight: 600; letter-spacing: 0.03em;
    text-transform: uppercase; padding: 0.12rem 0.45rem; border-radius: 99px; margin-left: 0.5rem;
    vertical-align: middle;
  }}
  .chip-muted {{ background: var(--surface-2); color: var(--ink-3); }}

  .cohort-intro {{
    background: var(--surface-2); border: 1px solid var(--line); border-radius: 10px;
    padding: 0.9rem 1.1rem; font-size: 0.84rem; color: var(--ink-2); margin-bottom: 1rem;
  }}
  .cohort-intro a {{ color: var(--accent); }}

  details.cohort {{
    background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
    box-shadow: var(--shadow); margin-bottom: 0.7rem; overflow: hidden;
  }}
  details.cohort[open] {{ padding-bottom: 0.2rem; }}
  details.cohort-control {{ border-color: var(--accent); }}
  summary {{
    list-style: none; cursor: pointer; padding: 0.85rem 1.1rem;
    display: flex; align-items: center;
  }}
  summary::-webkit-details-marker {{ display: none; }}
  summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: -2px; }}
  .cohort-summary {{
    display: flex; align-items: center; gap: 0.9rem; width: 100%; flex-wrap: wrap;
  }}
  .width-badge {{
    font-family: "IBM Plex Mono", monospace; font-weight: 600; font-size: 0.92rem;
    background: var(--surface-2); color: var(--ink); border: 1px solid var(--line);
    padding: 0.2rem 0.55rem; border-radius: 6px; min-width: 4.2rem; text-align: center;
  }}
  details.cohort-control .width-badge {{ background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }}
  .cohort-sub {{ color: var(--ink-3); font-size: 0.8rem; flex: 1 1 220px; }}
  .cohort-agg {{ color: var(--ink-2); font-size: 0.78rem; white-space: nowrap; }}
  .chevron {{
    width: 0.55rem; height: 0.55rem; border-right: 2px solid var(--ink-3); border-bottom: 2px solid var(--ink-3);
    transform: rotate(-45deg); transition: transform 0.15s ease; margin-left: 0.3rem; flex: 0 0 auto;
  }}
  details[open] .chevron {{ transform: rotate(45deg); }}
  .cohort-body {{ padding: 0 1.1rem 0.9rem; border-top: 1px solid var(--line); }}
  .cohort-body table {{ margin-top: 0.6rem; }}

  tr.row-flagged td.col-symbol {{ border-left: 3px solid var(--risk); padding-left: calc(0.6rem - 3px); }}
  .risk-flag {{
    margin-top: 0.2rem; font-family: "IBM Plex Sans", sans-serif; font-size: 0.72rem;
    color: var(--risk); background: var(--risk-bg); display: inline-block;
    padding: 0.15rem 0.45rem; border-radius: 5px; max-width: 46ch; line-height: 1.35;
  }}

  footer {{ margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid var(--line); color: var(--ink-3); font-size: 0.78rem; }}
  footer a {{ color: var(--accent); }}

  @media (prefers-reduced-motion: reduce) {{
    .chevron {{ transition: none; }}
  }}
</style>

<div class="wrap">
  <header class="masthead">
    <p class="eyebrow">crypto_mm_mexc · S8 liquidity provision</p>
    <h1>Spread Lab</h1>
    <p class="masthead-sub">Live paper-trade research and the spread-width forward-test cohort, read directly from <span class="mono">data/paper_trade_state.json</span>. Local to this repo — no capital, no live orders.</p>
    <div class="meta-strip">
      <span><b>{len(LIVE_PAIRS)}</b> live pairs</span>
      <span><b>{total_cohort}</b> cohort instances</span>
      <span><b>{len(LIVE_PAIRS) + total_cohort}</b> total tracked</span>
      <span>Last run: <b class="mono">{last_run}</b></span>
      <span>Generated: <b class="mono">{generated}</b></span>
    </div>
  </header>

  <section id="live">
    <h2>Live Research (MEXC)</h2>
    <p class="section-sub">The 7 original live pairs at 1.0% spread, on their original independent clocks. Unchanged by the cohort below.</p>
    <div class="live-table-wrap">
      <table>
        <thead>
          <tr><th>Pair</th><th>Started</th><th>Age</th><th>Fills</th><th>Complete</th><th>Forced</th><th>FC rate</th><th>Realized net</th></tr>
        </thead>
        <tbody>{live_rows}</tbody>
      </table>
    </div>
  </section>

  <section id="cohort">
    <h2>Spread-Width Cohort</h2>
    <p class="section-sub">7 pairs × 6 widths (0.5%–0.9% + a fresh 1.0% control), all started 2026-08-22 — forward, out-of-sample test of the spread-width backtest sweeps. Collapsed by default; click a row to expand.</p>
    <div class="cohort-intro">
      Two single-window backtests disagreed on which width performs best — see <span class="mono">docs/SPREAD_WIDTH_COHORT_2026-08-22.md</span> for why that's not conclusive on its own, including the specific PIPPIN and XYO findings that motivated this forward test. Re-check planned 2026-09-15 – 2026-09-21.
    </div>
    {cohort_sections}
  </section>

  <footer>
    Generated by <span class="mono">src/dashboard.py</span> from local state only. See <span class="mono">PAPER_TRADE.md</span>, <span class="mono">GATE.md</span>, and <span class="mono">docs/SPREAD_WIDTH_COHORT_2026-08-22.md</span> for methodology.
  </footer>
</div>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).parent.parent / "docs" / "dashboard.html"))
    args = parser.parse_args()

    state = load_state()
    html_out = render(state)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
