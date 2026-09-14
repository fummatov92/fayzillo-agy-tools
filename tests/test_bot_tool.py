import os
import sys
import unittest
import shutil

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from agy_tools.modules.bot_tool import add_handler, remove_handler, list_handlers, check_handlers

class TestBotTool(unittest.TestCase):
    def setUp(self):
        self.test_handlers_dir = os.path.join(parent_dir, "tests_temp_handlers")
        os.makedirs(self.test_handlers_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_handlers_dir):
            shutil.rmtree(self.test_handlers_dir)

    def test_01_add_and_list_handler(self):
        res = add_handler("test_cmd", description="Test buyrugi", handlers_dir=self.test_handlers_dir)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["name"], "test_cmd")
        
        target_path = os.path.join(self.test_handlers_dir, "test_cmd.js")
        self.assertTrue(os.path.exists(target_path))

        listed = list_handlers(handlers_dir=self.test_handlers_dir)
        self.assertTrue(listed["success"])
        self.assertEqual(listed["data"]["count"], 1)

    def test_02_remove_handler_normal(self):
        add_handler("to_delete", description="Delete me", handlers_dir=self.test_handlers_dir)
        target_path = os.path.join(self.test_handlers_dir, "to_delete.js")
        self.assertTrue(os.path.exists(target_path))

        res = remove_handler("to_delete", handlers_dir=self.test_handlers_dir)
        self.assertTrue(res["success"])
        self.assertFalse(os.path.exists(target_path))

    def test_03_remove_handler_blocks_path_traversal(self):
        # Specific attack vector testing
        with self.assertRaises(PermissionError):
            remove_handler("../../../tmp/pwned_test_file", handlers_dir=self.test_handlers_dir)
        self.assertFalse(os.path.exists("/tmp/pwned_test_file.js"))

    def test_04_add_handler_blocks_path_traversal(self):
        with self.assertRaises(PermissionError):
            add_handler("../../../tmp/evil_handler", handlers_dir=self.test_handlers_dir)
        self.assertFalse(os.path.exists("/tmp/evil_handler.js"))

if __name__ == "__main__":
    unittest.main()
