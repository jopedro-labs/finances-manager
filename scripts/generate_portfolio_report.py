"""Generate portfolio analysis reports in HTML or Markdown with Gemini and deterministic fallback.

Reads structured snapshot, opportunity metrics, and fundamental cache from SQLite,
passes enriched context to Gemini agents (analyst.md + reporter.md), and produces
reports/YYYY-MM-DD.html or reports/YYYY-MM-DD.md. Includes an automatic deterministic
local fallback in case the Gemini AI API is unavailable.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Ensure root directory is in pythonpath
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core_lib.file_utils.file_utils import load_file_content  # noqa: E402
from core_lib.logger import logger  # noqa: E402
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402
from google.genai.errors import APIError  # noqa: E402

from config import AGENTS_DIR, DATA_DIR, REPORTS_DIR, get_settings  # noqa: E402
from infra.database.connection import get_db_context  # noqa: E402
from infra.database.schema import initialize_database  # noqa: E402

RULES_FILE: Path = DATA_DIR / "rules.md"
ANALYST_FILE: Path = AGENTS_DIR / "analyst.md"
REPORTER_FILE: Path = AGENTS_DIR / "reporter.md"


def _load_sqlite_report_context(db_path: Path) -> dict[str, Any]:
    """Loads consolidated portfolio, opportunity metrics, and fundamentals from SQLite."""
    with get_db_context(str(db_path)) as conn:
        initialize_database(conn)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. Latest snapshot
        cur.execute(
            """
            SELECT id, timestamp, total_invested_eur, total_market_value_eur,
                   unrealized_pnl_eur, unrealized_pnl_pct, breakdown_json
            FROM portfolio_snapshots
            ORDER BY id DESC LIMIT 1
            """
        )
        snap_row = cur.fetchone()
        if not snap_row:
            return {}

        snapshot_id = snap_row["id"]
        snapshot_dict = dict(snap_row)
        if snapshot_dict.get("breakdown_json"):
            try:
                snapshot_dict["breakdown"] = json.loads(snapshot_dict["breakdown_json"])
            except Exception:
                snapshot_dict["breakdown"] = {}

        # 2. Holdings for this snapshot
        cur.execute(
            """
            SELECT a.name, a.yahoo_ticker, a.isin, a.asset_type,
                   sa.quantity, sa.invested_eur, sa.native_price,
                   sa.native_currency, sa.value_eur
            FROM asset_snapshots sa
            JOIN assets a ON sa.asset_id = a.id
            WHERE sa.snapshot_id = ?
            ORDER BY sa.value_eur DESC
            """,
            (snapshot_id,),
        )
        holdings = [dict(r) for r in cur.fetchall()]
        snapshot_dict["holdings"] = holdings

        # 3. Latest opportunity metrics run
        cur.execute(
            """
            SELECT id, timestamp, total_invested_eur, total_value_eur, unrealized_pnl_eur, has_ai
            FROM opportunities
            ORDER BY id DESC LIMIT 1
            """
        )
        opp_row = cur.fetchone()
        opp_dict: dict[str, Any] = dict(opp_row) if opp_row else {}

        if opp_row:
            opp_id = opp_row["id"]
            cur.execute(
                """
                SELECT symbol, asset_type, rank, price_eur, current_allocation_pct,
                       target_allocation_pct, dip_score, cost_score, gap_score,
                       quant_score, ai_action, ai_urgency, ai_confidence_pct
                FROM opportunity_asset_metrics
                WHERE opportunity_id = ?
                ORDER BY rank ASC
                """,
                (opp_id,),
            )
            opp_dict["ranked_metrics"] = [dict(r) for r in cur.fetchall()]

        # 4. Fundamentals quality ratings
        cur.execute(
            """
            SELECT a.name, a.yahoo_ticker, a.isin, af.asset_type, af.quality_tier,
                   af.quality_score, af.details_json
            FROM asset_fundamentals af
            JOIN assets a ON af.asset_id = a.id
            """
        )
        fundamentals: list[dict[str, Any]] = []
        for r in cur.fetchall():
            item = dict(r)
            if item.get("details_json"):
                try:
                    item["details"] = json.loads(item["details_json"])
                except Exception:
                    item["details"] = {}
            fundamentals.append(item)

        return {
            "snapshot": snapshot_dict,
            "opportunity_analysis": opp_dict,
            "fundamentals": fundamentals,
        }


def _generate_deterministic_fallback_report(context: dict[str, Any]) -> str:
    """Generates a complete Markdown report locally without external LLM calls."""
    snap = context.get("snapshot", {})
    opp = context.get("opportunity_analysis", {})
    holdings = snap.get("holdings", [])
    ranked_metrics = opp.get("ranked_metrics", [])

    total_value = float(snap.get("total_market_value_eur", 0.0))
    total_invested = float(snap.get("total_invested_eur", 0.0))
    unrealized_pnl = float(snap.get("unrealized_pnl_eur", 0.0))
    roi_pct = float(snap.get("unrealized_pnl_pct", 0.0))
    timestamp = snap.get("timestamp", str(datetime.date.today()))

    md: list[str] = [
        f"# Portfolio Analysis Report — {timestamp.split('T')[0]}",
        "",
        "> *Generated via Deterministic Fallback Engine (SQLite Source of Truth)*",
        "",
        "## Section 1 — Macro Summary",
        "",
        "| Portfolio Metric | Value |",
        "|---|---|",
        f"| **Total Market Value** | €{total_value:,.2f} |",
        f"| **Total Capital Invested** | €{total_invested:,.2f} |",
        f"| **Unrealized Gain / Loss** | €{unrealized_pnl:+,.2f} ({roi_pct:+.2f}%) |",
        f"| **Active Holdings Count** | {len(holdings)} assets |",
        "",
        "### Asset Class Breakdown",
        "",
    ]

    breakdown = snap.get("breakdown", {})
    stocks_eur = float(breakdown.get("stocks_eur", 0.0))
    etfs_eur = float(breakdown.get("etfs_eur", 0.0))
    stocks_pct = (stocks_eur / total_value * 100.0) if total_value > 0 else 0.0
    etfs_pct = (etfs_eur / total_value * 100.0) if total_value > 0 else 0.0

    md.extend(
        [
            f"- **Stocks Allocation:** €{stocks_eur:,.2f} ({stocks_pct:.1f}%)",
            f"- **ETFs Allocation:** €{etfs_eur:,.2f} ({etfs_pct:.1f}%)",
            "",
            "---",
            "",
            "## Section 2 — Holdings, Opportunities & Rebalance Recommendations",
            "",
            "| Rank | Asset / Symbol | Type | Current Alloc | Target Alloc | Quant Score | Recommendation |",
            "|---|---|---|---|---|---|---|",
        ]
    )

    for m in ranked_metrics:
        sym = m.get("symbol", "-")
        atype = m.get("asset_type", "-")
        curr_a = f"{m.get('current_allocation_pct', 0.0):.1f}%"
        tgt_a = f"{m.get('target_allocation_pct', 0.0):.1f}%"
        qscore = f"{m.get('quant_score', 0.0):.4f}"
        action = m.get("ai_action", "HOLD")
        badge = f"**{action}**"
        md.append(
            f"| #{m.get('rank', '-')} | `{sym}` | {atype} | {curr_a} | {tgt_a} | `{qscore}` | {badge} |"
        )

    md.extend(
        [
            "",
            "---",
            "",
            "## Section 3 — Long-Term Projections (Horizon Matrix)",
            "",
            "| Horizon | Conservative (5.0%) | Realistic (8.0%) | Optimistic (11.0%) |",
            "|---|---|---|---|",
        ]
    )

    for years in (10, 20, 30):
        # Base PV compound growth
        v_cons = total_value * ((1.05) ** years)
        v_real = total_value * ((1.08) ** years)
        v_opt = total_value * ((1.11) ** years)
        md.append(f"| **{years} Years** | €{v_cons:,.0f} | €{v_real:,.0f} | €{v_opt:,.0f} |")

    md.append("")
    return "\n".join(md)


def main() -> None:
    """Execute the portfolio analysis and reporting pipeline."""
    mode = sys.argv[1] if len(sys.argv) > 1 else "md"

    if mode not in ("md", "html"):
        logger.error(f"[generate report] Invalid mode '{mode}'. Use 'md' or 'html'.")
        sys.exit(1)

    settings = get_settings()
    db_path = settings.finance_db_file

    logger.section(f"[generate report] Generating Portfolio Report ({mode.upper()})")

    context_data = _load_sqlite_report_context(db_path)
    if not context_data.get("snapshot"):
        logger.error(
            "[generate report] No snapshot data available in SQLite. Run make snapshot first."
        )
        sys.exit(1)

    today_str: str = datetime.date.today().isoformat()
    output_filename: str = f"{today_str}.html" if mode == "html" else f"{today_str}.md"
    output_path: Path = REPORTS_DIR / output_filename
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    api_key = settings.gemini_api_key
    report_content: str | None = None

    if api_key:
        try:
            logger.info(
                "[generate report] Invoking Gemini AI model for narrative report generation..."
            )
            rules_content: str = load_file_content(RULES_FILE)
            analyst_content: str = load_file_content(ANALYST_FILE)
            reporter_content: str = load_file_content(REPORTER_FILE)

            system_instruction: str = (
                f"{rules_content}\n\n"
                f"--- ANALYST ROLE ---\n{analyst_content}\n\n"
                f"--- REPORTER ROLE ---\n{reporter_content}"
            )

            client = genai.Client(api_key=api_key)
            prompt = (
                f"Generate a daily portfolio analysis report in {mode.upper()} format.\n\n"
                f"SQLITE PORTFOLIO STATE, OPPORTUNITIES AND FUNDAMENTALS:\n"
                f"{json.dumps(context_data, indent=2)}\n\n"
                f"Apply all rules strictly. Today's date is {today_str}."
            )

            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                ),
            )
            report_content = response.text
            logger.success(
                "[generate report] Successfully received narrative report from Gemini AI."
            )
        except (APIError, Exception) as e:
            logger.warning(
                f"[generate report] Gemini API call failed or quota exceeded ({e}). "
                "Failing over to deterministic local report generation..."
            )
            report_content = None

    if not report_content:
        logger.info(
            "[generate report] Using deterministic fallback engine for report generation..."
        )
        report_content = _generate_deterministic_fallback_report(context_data)

    output_path.write_text(report_content, encoding="utf-8")
    logger.success(f"[generate report] Report successfully written to '{output_path}'.")


if __name__ == "__main__":
    main()
