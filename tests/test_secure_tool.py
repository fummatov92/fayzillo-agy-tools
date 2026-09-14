import os
import sys
import unittest
import tempfile
import shutil

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from agy_tools.modules.secure_tool import redact_text, run_secure_scan, run_secure_redact
import argparse

class TestSecureTool(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(parent_dir, "tests_temp_secure_test")
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_01_redact_text(self):
        sample = 'BOT_TOKEN = "1234567890:abcdefghijklmnopqrstuvwxyzABCDEFGHIJK"\nDB_PASS="P@ssw0rd_Secret123!"'
        redacted, count = redact_text(sample)
        self.assertGreater(count, 0)
        self.assertNotIn("1234567890:abcdefghijklmnopqrstuvwxyzABCDEFGHIJK", redacted)
        self.assertNotIn("P@ssw0rd_Secret123!", redacted)
        self.assertIn("[REDACTED_", redacted)

    def test_02_recursive_directory_redact(self):
        f1 = os.path.join(self.test_dir, "app.txt")
        f2 = os.path.join(self.test_dir, "config.json")
        with open(f1, "w") as fp:
            fp.write('TELEGRAM_TOKEN="1234567890:abcdefghijklmnopqrstuvwxyzABCDEFGHIJK"')
        with open(f2, "w") as fp:
            fp.write('{"password": "P@ssw0rd_Secret123!"}')

        # Test dry-run
        args_dry = argparse.Namespace(path=self.test_dir, dry_run=True)
        run_secure_redact(args_dry)

        # File contents should still have secrets
        with open(f1, "r") as fp:
            self.assertIn("1234567890:abcdefghijklmnopqrstuvwxyzABCDEFGHIJK", fp.read())

        # Test actual redaction
        args_real = argparse.Namespace(path=self.test_dir, dry_run=False)
        run_secure_redact(args_real)

        # File contents should now be redacted
        with open(f1, "r") as fp:
            content1 = fp.read()
            self.assertNotIn("1234567890:abcdefghijklmnopqrstuvwxyzABCDEFGHIJK", content1)
            self.assertIn("[REDACTED_", content1)

    def test_03_ignore_env_and_package_dirs(self):
        # Create .env file
        env_file = os.path.join(self.test_dir, ".env")
        with open(env_file, "w") as fp:
            fp.write('SECRET_KEY="1234567890:abcdefghijklmnopqrstuvwxyzABCDEFGHIJK"')

        # Create node_modules file
        nm_dir = os.path.join(self.test_dir, "node_modules", "package_a")
        os.makedirs(nm_dir, exist_ok=True)
        nm_file = os.path.join(nm_dir, "index.json")
        with open(nm_file, "w") as fp:
            fp.write('{"api_token": "1234567890:abcdefghijklmnopqrstuvwxyzABCDEFGHIJK"}')

        # Create vendor file
        vendor_dir = os.path.join(self.test_dir, "vendor", "bundle")
        os.makedirs(vendor_dir, exist_ok=True)
        vendor_file = os.path.join(vendor_dir, "config.json")
        with open(vendor_file, "w") as fp:
            fp.write('{"key": "1234567890:abcdefghijklmnopqrstuvwxyzABCDEFGHIJK"}')

        # Scan should ignore .env, node_modules, and vendor
        args_scan = argparse.Namespace(path=self.test_dir)
        run_secure_scan(args_scan)

        # Redact should also ignore them
        args_redact = argparse.Namespace(path=self.test_dir, dry_run=False)
        run_secure_redact(args_redact)

        # .env should remain untouched
        with open(env_file, "r") as fp:
            self.assertIn("1234567890:abcdefghijklmnopqrstuvwxyzABCDEFGHIJK", fp.read())

        # node_modules file should remain untouched
        with open(nm_file, "r") as fp:
            self.assertIn("1234567890:abcdefghijklmnopqrstuvwxyzABCDEFGHIJK", fp.read())

if __name__ == "__main__":
    unittest.main()
