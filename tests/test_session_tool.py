import unittest
import os
import sys
import json

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from agy_tools.modules import session_tool

class TestSessionTool(unittest.TestCase):
    def test_clean_user_prompt(self):
        raw = "<USER_REQUEST>\n[USER REQUEST]: Hello Jarvis!\n<ADDITIONAL_METADATA>\ntime=123\n</ADDITIONAL_METADATA>\n</USER_REQUEST>"
        cleaned = session_tool.clean_user_prompt(raw)
        self.assertEqual(cleaned, "Hello Jarvis!")

    def test_describe(self):
        desc = session_tool.get_session_describe()
        self.assertEqual(desc["name"], "session")
        self.assertIn("list", desc["commands"])
        self.assertIn("inspect", desc["commands"])
        self.assertIn("query", desc["commands"])
        self.assertIn("export", desc["commands"])

if __name__ == "__main__":
    unittest.main()
