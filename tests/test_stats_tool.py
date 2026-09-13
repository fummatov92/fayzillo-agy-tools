import os
import sys
import unittest
import json

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from agy_tools.modules.stats_tool import StatsCalculator, format_stats_table

class TestStatsTool(unittest.TestCase):
    def setUp(self):
        self.calc = StatsCalculator()

    def test_01_compare_tool(self):
        res = self.calc.compare_tool("face")
        self.assertEqual(res["tool"], "face")
        self.assertGreater(res["tokens_saved_per_operation"], 2000)
        self.assertIn("x tezroq", res["speedup_factor"])

    def test_02_compare_all_tools(self):
        for tool in ["face", "media", "super-media", "code", "doc", "session", "debug", "secure", "sys", "stats"]:
            res = self.calc.compare_tool(tool)
            self.assertEqual(res["tool"], tool)
            self.assertGreater(res["raw_tokens_per_operation"], res["tool_tokens_per_operation"])

    def test_03_format_stats_table(self):
        dummy_res = {
            "session_id": "test-session-1234",
            "total_steps": 10,
            "tool_calls_count": 5,
            "tool_breakdown": {"run_command": 3, "view_file": 2},
            "tokens": {
                "estimated_raw_llm": 42000,
                "tool_augmented_actual": 2050,
                "tokens_saved": 39950,
                "savings_percentage": 95.1
            },
            "financial_roi": {
                "pricing_model": "Claude 3.5 Sonnet ($3.00/1M tokens)",
                "estimated_raw_cost_usd": 0.1260,
                "actual_tool_cost_usd": 0.0062,
                "money_saved_usd": 0.1198
            },
            "time_and_speed": {
                "estimated_raw_time_seconds": 66.0,
                "actual_tool_time_seconds": 0.7,
                "speedup_factor": "94.3x tezroq"
            }
        }
        table_str = format_stats_table(dummy_res)
        self.assertIn("Token & ROI Tahlili", table_str)
        self.assertIn("95.1%", table_str)
        self.assertIn("0.1198", table_str)

if __name__ == "__main__":
    unittest.main()
