import os
import sys
import shutil
import zipfile
import unittest
from pathlib import Path

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from agy_tools.modules.archive_tool import pack_archive, unpack_archive, is_excluded

class TestArchiveTool(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(parent_dir, "tests_temp_archive_test")
        os.makedirs(self.test_dir, exist_ok=True)
        self.src_dir = os.path.join(self.test_dir, "src_project")
        os.makedirs(self.src_dir, exist_ok=True)

        # Create dummy structure
        # Normal files
        os.makedirs(os.path.join(self.src_dir, "src", "components"), exist_ok=True)
        with open(os.path.join(self.src_dir, "src", "index.ts"), "w") as f:
            f.write("console.log('hello');")
        with open(os.path.join(self.src_dir, "src", "components", "Button.tsx"), "w") as f:
            f.write("export const Button = () => null;")
        with open(os.path.join(self.src_dir, "README.md"), "w") as f:
            f.write("# Sample Project")

        # Excluded / Secret / Junk files & dirs
        os.makedirs(os.path.join(self.src_dir, "node_modules", "pkg"), exist_ok=True)
        with open(os.path.join(self.src_dir, "node_modules", "pkg", "index.js"), "w") as f:
            f.write("module.exports = {};")

        os.makedirs(os.path.join(self.src_dir, ".git", "objects"), exist_ok=True)
        with open(os.path.join(self.src_dir, ".git", "config"), "w") as f:
            f.write("[core]")

        os.makedirs(os.path.join(self.src_dir, "dist"), exist_ok=True)
        with open(os.path.join(self.src_dir, "dist", "bundle.js"), "w") as f:
            f.write("compiled code")

        with open(os.path.join(self.src_dir, ".env"), "w") as f:
            f.write("SECRET_KEY=supersecret")

        with open(os.path.join(self.src_dir, "private_key.pem"), "w") as f:
            f.write("-----BEGIN PRIVATE KEY-----")

        with open(os.path.join(self.src_dir, "app.log"), "w") as f:
            f.write("debug log")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_exclusion_helper(self):
        self.assertTrue(is_excluded("node_modules/foo/bar.js", False))
        self.assertTrue(is_excluded(".git/config", False))
        self.assertTrue(is_excluded("dist/bundle.js", False))
        self.assertTrue(is_excluded(".env", False))
        self.assertTrue(is_excluded("server.key", False))
        self.assertTrue(is_excluded("logs/error.log", False))
        self.assertFalse(is_excluded("src/index.ts", False))
        self.assertFalse(is_excluded("README.md", False))

    def test_pack_clean_archive(self):
        out_zip = os.path.join(self.test_dir, "output.zip")
        res = pack_archive(self.src_dir, output_path=out_zip, clean=True)

        self.assertTrue(os.path.exists(out_zip))
        self.assertIn("data", res)
        self.assertEqual(res["data"]["total_files"], 3) # index.ts, Button.tsx, README.md

        # Verify ZIP content
        with zipfile.ZipFile(out_zip, 'r') as z:
            names = set(z.namelist())
            self.assertIn("src/index.ts", names)
            self.assertIn("src/components/Button.tsx", names)
            self.assertIn("README.md", names)
            self.assertNotIn(".env", names)
            self.assertNotIn("private_key.pem", names)
            self.assertNotIn("app.log", names)
            self.assertNotIn("node_modules/pkg/index.js", names)
            self.assertNotIn(".git/config", names)
            self.assertNotIn("dist/bundle.js", names)

    def test_pack_custom_excludes(self):
        out_zip = os.path.join(self.test_dir, "custom.zip")
        res = pack_archive(self.src_dir, output_path=out_zip, clean=True, exclude="*.tsx,README*")

        self.assertTrue(os.path.exists(out_zip))
        with zipfile.ZipFile(out_zip, 'r') as z:
            names = set(z.namelist())
            self.assertIn("src/index.ts", names)
            self.assertNotIn("src/components/Button.tsx", names)
            self.assertNotIn("README.md", names)

    def test_unpack_archive_normal(self):
        out_zip = os.path.join(self.test_dir, "output.zip")
        pack_archive(self.src_dir, output_path=out_zip, clean=True)

        target_dir = os.path.join(self.test_dir, "extracted")
        res = unpack_archive(out_zip, target_dir=target_dir)

        self.assertIn("data", res)
        self.assertEqual(res["data"]["extracted_files_count"], 3)
        self.assertTrue(os.path.exists(os.path.join(target_dir, "src", "index.ts")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "src", "components", "Button.tsx")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "README.md")))

    def test_unpack_windows_backslashes(self):
        # Create a ZIP with Windows-style backslashes in member names
        win_zip = os.path.join(self.test_dir, "windows_style.zip")
        with zipfile.ZipFile(win_zip, 'w') as z:
            z.writestr(r"nested\folder\file.txt", "content inside windows path")
            z.writestr(r"root_file.txt", "root content")

        target_dir = os.path.join(self.test_dir, "extracted_win")
        unpack_archive(win_zip, target_dir=target_dir)

        self.assertTrue(os.path.exists(os.path.join(target_dir, "nested", "folder", "file.txt")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "root_file.txt")))
        # Ensure no literal backslash file exists
        self.assertFalse(os.path.exists(os.path.join(target_dir, r"nested\folder\file.txt")))

    def test_unpack_zip_slip_prevention(self):
        # Create a malicious ZIP trying to escape target dir
        bad_zip = os.path.join(self.test_dir, "malicious.zip")
        with zipfile.ZipFile(bad_zip, 'w') as z:
            z.writestr("../../evil.txt", "hacked")

        target_dir = os.path.join(self.test_dir, "extracted_safe")
        with self.assertRaises(PermissionError):
            unpack_archive(bad_zip, target_dir=target_dir)

if __name__ == "__main__":
    unittest.main()
