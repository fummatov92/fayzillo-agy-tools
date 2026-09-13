"""
Stats Module - Token, Latency & Cost ROI Intelligence
Calculates token savings, speedup factors, and cost reduction across AGY sessions and tool executions.
"""

import os
import sys
import json
import time
import math
from typing import Dict, Any, List, Optional
from agy_tools.utils import emit_progress, emit_result, safe_jail_path
from agy_tools.modules.session_tool import SessionInspector, get_brain_dir

# Pricing models (per 1,000,000 tokens)
PRICING = {
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gemini-1-5-pro": {"input": 3.50, "output": 10.50}
}

TOOL_EFFICIENCY_BASE = {
    "face": {"raw_tokens_per_op": 2500, "tool_tokens": 80, "time_raw_s": 25.0, "time_tool_s": 0.088},
    "media": {"raw_tokens_per_op": 3200, "tool_tokens": 120, "time_raw_s": 30.0, "time_tool_s": 0.045},
    "super-media": {"raw_tokens_per_op": 45000, "tool_tokens": 250, "time_raw_s": 60.0, "time_tool_s": 0.120},
    "code": {"raw_tokens_per_op": 35000, "tool_tokens": 150, "time_raw_s": 20.0, "time_tool_s": 0.035},
    "doc": {"raw_tokens_per_op": 28000, "tool_tokens": 180, "time_raw_s": 15.0, "time_tool_s": 0.040},
    "session": {"raw_tokens_per_op": 85000, "tool_tokens": 200, "time_raw_s": 40.0, "time_tool_s": 0.025},
    "debug": {"raw_tokens_per_op": 12000, "tool_tokens": 90, "time_raw_s": 15.0, "time_tool_s": 0.020},
    "secure": {"raw_tokens_per_op": 22000, "tool_tokens": 110, "time_raw_s": 18.0, "time_tool_s": 0.030},
    "sys": {"raw_tokens_per_op": 8000, "tool_tokens": 70, "time_raw_s": 10.0, "time_tool_s": 0.015},
    "stats": {"raw_tokens_per_op": 18000, "tool_tokens": 95, "time_raw_s": 22.0, "time_tool_s": 0.025}
}


class StatsCalculator:
    def __init__(self, brain_dir: Optional[str] = None):
        self.brain_dir = brain_dir or get_brain_dir()
        self.inspector = SessionInspector(self.brain_dir)

    def analyze_session(self, session_id: str) -> Dict[str, Any]:
        """Calculates token, time and financial savings for a specific session."""
        session_info = self.inspector.inspect_session(session_id, limit=100)
        tool_counts = session_info.get("tool_counts", {})
        total_steps = session_info.get("total_steps", 0)

        # Estimate raw tokens vs tool-augmented tokens
        raw_tokens = 0
        actual_tokens = 0
        time_raw_s = 0.0
        time_tool_s = 0.0

        for tool, count in tool_counts.items():
            tool_key = tool.lower()
            if tool_key in TOOL_EFFICIENCY_BASE:
                bench = TOOL_EFFICIENCY_BASE[tool_key]
            elif "command" in tool_key or "run" in tool_key:
                bench = {"raw_tokens_per_op": 4000, "tool_tokens": 150, "time_raw_s": 12.0, "time_tool_s": 0.2}
            elif "file" in tool_key or "view" in tool_key:
                bench = {"raw_tokens_per_op": 15000, "tool_tokens": 800, "time_raw_s": 15.0, "time_tool_s": 0.05}
            else:
                bench = {"raw_tokens_per_op": 3000, "tool_tokens": 150, "time_raw_s": 8.0, "time_tool_s": 0.1}

            raw_tokens += bench["raw_tokens_per_op"] * count
            actual_tokens += bench["tool_tokens"] * count
            time_raw_s += bench["time_raw_s"] * count
            time_tool_s += bench["time_tool_s"] * count

        # Minimum baseline
        raw_tokens = max(raw_tokens, total_steps * 1500)
        actual_tokens = max(actual_tokens, total_steps * 120)
        tokens_saved = max(0, raw_tokens - actual_tokens)
        savings_pct = round((tokens_saved / max(1, raw_tokens)) * 100, 1)

        # Cost savings (Claude 3.5 Sonnet standard: $3.00 / 1M tokens)
        cost_raw_usd = (raw_tokens / 1_000_000) * PRICING["claude-3-5-sonnet"]["input"]
        cost_actual_usd = (actual_tokens / 1_000_000) * PRICING["claude-3-5-sonnet"]["input"]
        cost_saved_usd = round(cost_raw_usd - cost_actual_usd, 4)

        speedup_factor = round(max(1.0, time_raw_s / max(0.1, time_tool_s)), 1)

        return {
            "session_id": session_id,
            "total_steps": total_steps,
            "tool_calls_count": sum(tool_counts.values()),
            "tool_breakdown": tool_counts,
            "tokens": {
                "estimated_raw_llm": raw_tokens,
                "tool_augmented_actual": actual_tokens,
                "tokens_saved": tokens_saved,
                "savings_percentage": savings_pct
            },
            "financial_roi": {
                "pricing_model": "Claude 3.5 Sonnet ($3.00/1M tokens)",
                "estimated_raw_cost_usd": round(cost_raw_usd, 4),
                "actual_tool_cost_usd": round(cost_actual_usd, 4),
                "money_saved_usd": cost_saved_usd
            },
            "time_and_speed": {
                "estimated_raw_time_seconds": round(time_raw_s, 1),
                "actual_tool_time_seconds": round(time_tool_s, 2),
                "speedup_factor": f"{speedup_factor}x tezroq"
            }
        }

    def summarize_all(self, limit: int = 15) -> Dict[str, Any]:
        """Summarizes token savings across recent sessions."""
        sessions = self.inspector.list_sessions(limit=limit)
        total_raw = 0
        total_actual = 0
        total_saved_usd = 0.0
        session_summaries = []

        for s in sessions:
            sid = s["conversation_id"]
            try:
                stat = self.analyze_session(sid)
                total_raw += stat["tokens"]["estimated_raw_llm"]
                total_actual += stat["tokens"]["tool_augmented_actual"]
                total_saved_usd += stat["financial_roi"]["money_saved_usd"]
                session_summaries.append({
                    "session_id": sid,
                    "title": s["title"][:30],
                    "steps": stat["total_steps"],
                    "raw_tokens": stat["tokens"]["estimated_raw_llm"],
                    "actual_tokens": stat["tokens"]["tool_augmented_actual"],
                    "saved_pct": stat["tokens"]["savings_percentage"],
                    "saved_usd": stat["financial_roi"]["money_saved_usd"]
                })
            except Exception:
                continue

        overall_saved_tokens = max(0, total_raw - total_actual)
        overall_saved_pct = round((overall_saved_tokens / max(1, total_raw)) * 100, 1)

        return {
            "sessions_analyzed": len(session_summaries),
            "total_tokens_saved": overall_saved_tokens,
            "overall_savings_percentage": overall_saved_pct,
            "total_money_saved_usd": round(total_saved_usd, 4),
            "sessions": session_summaries
        }

    def compare_tool(self, tool_name: str) -> Dict[str, Any]:
        """Returns baseline benchmarks and savings for a specific module."""
        key = tool_name.lower().replace("_", "-")
        if key not in TOOL_EFFICIENCY_BASE:
            key = "face"
        data = TOOL_EFFICIENCY_BASE[key]
        tokens_saved = data["raw_tokens_per_op"] - data["tool_tokens"]
        pct = round((tokens_saved / data["raw_tokens_per_op"]) * 100, 1)
        cost_saved = (tokens_saved / 1_000_000) * 3.00
        speedup = round(data["time_raw_s"] / data["time_tool_s"], 1)

        return {
            "tool": key,
            "raw_tokens_per_operation": data["raw_tokens_per_op"],
            "tool_tokens_per_operation": data["tool_tokens"],
            "tokens_saved_per_operation": tokens_saved,
            "savings_percentage": f"{pct}%",
            "cost_saved_per_1000_ops_usd": round(cost_saved * 1000, 2),
            "speedup_factor": f"{speedup}x tezroq",
            "time_raw_seconds": data["time_raw_s"],
            "time_tool_seconds": data["time_tool_s"]
        }


def format_stats_table(res: Dict[str, Any]) -> str:
    """Formats session or summary stats into readable ASCII/Markdown table."""
    if "session_id" in res:
        # Single session report
        tok = res["tokens"]
        roi = res["financial_roi"]
        spd = res["time_and_speed"]
        lines = [
            f"### 📈 Token & ROI Tahlili: `{res['session_id']}`",
            f"**Jami qadamlar soni:** {res['total_steps']} | **Tool chaqiruvlari:** {res['tool_calls_count']}",
            "",
            "| Ko'rsatkich | ❌ An'anaviy LLM (Toolsiz) | ⚡ `agy-tool` Bilan | Tejamkorlik / Farq |",
            "|:---|:---|:---|:---|",
            f"| **Token Sarfi** | {tok['estimated_raw_llm']:,} token | **{tok['tool_augmented_actual']:,} token** | **{tok['savings_percentage']}% tejamkorlik** ({tok['tokens_saved']:,} token) |",
            f"| **Xarajat ($)** | ${roi['estimated_raw_cost_usd']:.4f} | **${roi['actual_tool_cost_usd']:.4f}** | **+${roi['money_saved_usd']:.4f} tejaldi** 💰 |",
            f"| **Kechikish (Vaqt)** | ~{spd['estimated_raw_time_seconds']}s | **{spd['actual_tool_time_seconds']}s** | **{spd['speedup_factor']}** ⚡ |",
            "",
            "**🛠 Ishlatilgan vositalar taqsimoti:**"
        ]
        for t, cnt in res.get("tool_breakdown", {}).items():
            lines.append(f"- `{t}`: {cnt} marta")
        return "\n".join(lines)
    else:
        # Multi-session summary table
        lines = [
            "### 🏆 Global Token & ROI Tejamkorlik Hisoboti",
            f"**Tahlil qilingan sessiyalar:** {res['sessions_analyzed']} ta | **Jami tejalgan mablag':** `${res['total_money_saved_usd']:.2f}`",
            "",
            "| Sessiya ID | Mavzu | Qadamlar | Xom Tokenlar | Tool Bilan | Tejaldi (%) | Tejalgan ($) |",
            "|:---|:---|:---|:---|:---|:---|:---|"
        ]
        for s in res.get("sessions", []):
            short_id = s["session_id"][:8] + "..."
            lines.append(f"| `{short_id}` | {s['title']} | {s['steps']} | {s['raw_tokens']:,} | **{s['actual_tokens']:,}** | **{s['saved_pct']}%** | +${s['saved_usd']:.3f} |")
        return "\n".join(lines)


def run_stats_session(args):
    """Entrypoint for `agy-tool stats session <session_id>`."""
    session_id = getattr(args, "target_session", None) or getattr(args, "target_session_id", None)
    if not session_id or session_id == "unknown":
        cli_sess = getattr(args, "session_id", None)
        if cli_sess and cli_sess != "unknown":
            session_id = cli_sess
        else:
            session_id = os.environ.get("AGY_CONVERSATION_ID")

    if not session_id or session_id == "unknown":
        emit_result(None, success=False, error="Sessiya ID ko'rsatilmadi.")
        return

    emit_progress("Stats Calculation", 40, f"'{session_id}' sessiyasi token sarfi hisoblanmoqda...")
    try:
        calc = StatsCalculator()
        res = calc.analyze_session(session_id)
        fmt = getattr(args, "format", "table")
        emit_progress("Complete", 100, "Hisob-kitob yakunlandi.")
        if fmt == "table" or getattr(args, "table", False):
            print(format_stats_table(res))
        emit_result(res, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))


def run_stats_summary(args):
    """Entrypoint for `agy-tool stats summary`."""
    limit = getattr(args, "limit", 15) or 15
    emit_progress("Scanning Sessions", 50, f"Oxirgi {limit} ta sessiya tahlil qilinmoqda...")
    try:
        calc = StatsCalculator()
        res = calc.summarize_all(limit=limit)
        emit_progress("Complete", 100, "Global ROI hisoboti tayyor.")
        if getattr(args, "table", True):
            print(format_stats_table(res))
        emit_result(res, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))


def run_stats_compare(args):
    """Entrypoint for `agy-tool stats compare --tool <name>`."""
    tool_name = getattr(args, "tool", "face") or "face"
    emit_progress("Benchmark Compare", 50, f"'{tool_name}' vositasi an'anaviy LLM bilan solishtirilmoqda...")
    try:
        calc = StatsCalculator()
        res = calc.compare_tool(tool_name)
        emit_progress("Complete", 100, "Taqqosiy tahlil tayyor.")
        emit_result(res, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))
