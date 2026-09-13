import os
import sys
import math
import shutil
import unittest
import zipfile
import tarfile
import struct
import wave
import subprocess
from io import StringIO
from unittest.mock import patch
from PIL import Image, ImageDraw

# Ensure parent dir is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from agy_tools.modules import super_media_tool, media_tool
from agy_tools.utils import safe_jail_path


TEST_TEMP_DIR = os.path.join(parent_dir, "tests_temp_super_media")


def setup_temp_dir():
    os.makedirs(TEST_TEMP_DIR, exist_ok=True)
    return TEST_TEMP_DIR


def cleanup_temp_dir():
    if os.path.exists(TEST_TEMP_DIR):
        shutil.rmtree(TEST_TEMP_DIR, ignore_errors=True)


def create_synthetic_video(filepath: str, duration: int = 3):
    """Creates a small synthetic test MP4 video with video and audio streams using ffmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-c:a", "aac",
        filepath
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def create_synthetic_image(filepath: str, color=(255, 0, 0), width: int = 100, height: int = 100):
    """Creates a synthetic image for dHash tests."""
    img = Image.new("RGB", (width, height), color=color)
    img.save(filepath)
    return filepath


def create_synthetic_zip(filepath: str):
    """Creates a synthetic multi-category ZIP archive."""
    with zipfile.ZipFile(filepath, "w") as zf:
        # Docs
        zf.writestr("README.md", "# Super Media Project\nAn autonomous media reduction pipeline.\n")
        zf.writestr("docs/architecture.md", "# Architecture\nModular design.\n")
        # Config
        zf.writestr("package.json", '{"name": "super-media-app", "version": "1.0.0", "description": "High performance media toolkit", "dependencies": {"react": "^18.0.0", "express": "^4.18.0"}}')
        zf.writestr("Dockerfile", "FROM node:18-alpine\nWORKDIR /app\n")
        # Code
        zf.writestr("src/index.ts", "console.log('Running super media');\n")
        zf.writestr("src/routes/video.ts", "export const route = '/video';\n")
        # Media
        zf.writestr("assets/logo.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")
        # Trash / Build
        zf.writestr("node_modules/dummy/index.js", "// dependency\n")
        zf.writestr("dist/bundle.js", "// compiled bundle\n")


def create_synthetic_tar(filepath: str):
    """Creates a synthetic TAR archive."""
    with tarfile.open(filepath, "w:gz") as tf:
        import io
        readme_data = b"# Python FastAPI Backend\nHigh speed API service."
        ti = tarfile.TarInfo(name="README.md")
        ti.size = len(readme_data)
        tf.addfile(ti, io.BytesIO(readme_data))

        pyproject_data = b'[project]\nname = "fastapi-core"\nversion = "0.1.0"\ndescription = "Core FastAPI backend"\ndependencies = ["fastapi", "uvicorn"]\n'
        ti_py = tarfile.TarInfo(name="pyproject.toml")
        ti_py.size = len(pyproject_data)
        tf.addfile(ti_py, io.BytesIO(pyproject_data))

        code_data = b"from fastapi import FastAPI\napp = FastAPI()\n"
        ti_code = tarfile.TarInfo(name="src/main.py")
        ti_code.size = len(code_data)
        tf.addfile(ti_code, io.BytesIO(code_data))


class TestSuperMediaPerceptualDHash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work_dir = setup_temp_dir()

    @classmethod
    def tearDownClass(cls):
        cleanup_temp_dir()

    def test_dhash_computation_and_hamming(self):
        img1_path = os.path.join(self.work_dir, "img1.png")
        img2_path = os.path.join(self.work_dir, "img2.png")
        img3_path = os.path.join(self.work_dir, "img3.png")

        create_synthetic_image(img1_path, color=(255, 0, 0))
        create_synthetic_image(img2_path, color=(254, 0, 0))  # Near identical
        
        # Create distinctly patterned image
        img3 = Image.new("RGB", (100, 100), color=(0, 0, 0))
        draw = ImageDraw.Draw(img3)
        draw.rectangle([0, 0, 50, 100], fill=(255, 255, 255))
        img3.save(img3_path)

        hash1 = super_media_tool.compute_image_dhash(img1_path)
        hash2 = super_media_tool.compute_image_dhash(img2_path)
        hash3 = super_media_tool.compute_image_dhash(img3_path)

        self.assertEqual(len(hash1), 16)
        self.assertEqual(len(hash2), 16)
        self.assertEqual(len(hash3), 16)

        dist_identical = super_media_tool.hamming_distance(hash1, hash2)
        diff_identical = super_media_tool.dhash_difference_ratio(hash1, hash2)
        self.assertLess(diff_identical, 0.12, "Near-identical images should have diff < 12%")

        diff_distinct = super_media_tool.dhash_difference_ratio(hash1, hash3)
        self.assertGreaterEqual(diff_distinct, 0.12, "Patterned image should have significant diff")

    def test_reduce_frames_by_dhash(self):
        # 5 identical frames and 2 different frames
        raw_frames = [
            {"path": "", "timestamp_sec": 0.0, "dhash": "0000000000000000"},
            {"path": "", "timestamp_sec": 1.0, "dhash": "0000000000000000"},  # dup
            {"path": "", "timestamp_sec": 2.0, "dhash": "0000000000000001"},  # 1 bit diff (<12%) -> dup
            {"path": "", "timestamp_sec": 3.0, "dhash": "ffffffffffffffff"},  # completely different -> new keyframe
            {"path": "", "timestamp_sec": 4.0, "dhash": "fffffffffffffffe"},  # 1 bit diff -> dup
        ]

        reduced = super_media_tool.reduce_frames_by_dhash(raw_frames, threshold=0.12)
        self.assertEqual(len(reduced), 2, "Expected 2 unique keyframes after reduction")
        self.assertEqual(reduced[0]["merged_frames_count"], 3)
        self.assertEqual(reduced[1]["merged_frames_count"], 2)
        self.assertEqual(reduced[0]["duration_sec"], 3.0)


class TestSuperMediaAudioVisualTimeline(unittest.TestCase):
    def test_timeline_sync_and_table_generation(self):
        keyframes = [
            {
                "keyframe_id": 1,
                "filename": "frame_0001.jpg",
                "timestamp_sec": 0.0,
                "end_timestamp_sec": 15.0,
                "time_formatted": "00:00",
                "end_time_formatted": "00:15",
                "dhash": "a1b2c3d4e5f60718",
                "merged_frames_count": 15
            },
            {
                "keyframe_id": 2,
                "filename": "frame_0016.jpg",
                "timestamp_sec": 15.0,
                "end_timestamp_sec": 30.0,
                "time_formatted": "00:15",
                "end_time_formatted": "00:30",
                "dhash": "f9e8d7c6b5a41320",
                "merged_frames_count": 15
            }
        ]

        audio_segments = [
            {
                "chunk_id": 1,
                "start_seconds": 0.0,
                "end_seconds": 15.0,
                "time_range": "00:00 - 00:15",
                "text": "Loyiha taqdimotiga xush kelibsiz"
            },
            {
                "chunk_id": 2,
                "start_seconds": 15.0,
                "end_seconds": 30.0,
                "time_range": "00:15 - 00:30",
                "text": "Arxitektura va modullar tahlili"
            }
        ]

        events = super_media_tool.build_audio_visual_timeline(keyframes, audio_segments)
        self.assertEqual(len(events), 2)
        self.assertIn("Loyiha taqdimotiga", events[0]["speech_transcript"])
        self.assertIn("Arxitektura", events[1]["speech_transcript"])

        table_md = super_media_tool.generate_timeline_markdown_table(events)
        self.assertIn("Audio-Visual Timeline Digest", table_md)
        self.assertIn("Loyiha taqdimotiga", table_md)
        self.assertIn("frame_0001.jpg", table_md)


class TestSuperMediaCategorizedArchive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work_dir = setup_temp_dir()
        cls.zip_path = os.path.join(cls.work_dir, "test_archive.zip")
        cls.tar_path = os.path.join(cls.work_dir, "test_archive.tar.gz")
        create_synthetic_zip(cls.zip_path)
        create_synthetic_tar(cls.tar_path)

    @classmethod
    def tearDownClass(cls):
        cleanup_temp_dir()

    def test_category_matching(self):
        self.assertEqual(super_media_tool.match_file_category("README.md"), "docs")
        self.assertEqual(super_media_tool.match_file_category("docs/intro.txt"), "docs")
        self.assertEqual(super_media_tool.match_file_category("package.json"), "config")
        self.assertEqual(super_media_tool.match_file_category("Dockerfile"), "config")
        self.assertEqual(super_media_tool.match_file_category("src/app.ts"), "code")
        self.assertEqual(super_media_tool.match_file_category("routes/api.py"), "code")
        self.assertEqual(super_media_tool.match_file_category("assets/banner.png"), "media")
        self.assertEqual(super_media_tool.match_file_category("node_modules/react/index.js"), "trash_build")
        self.assertEqual(super_media_tool.match_file_category("dist/bundle.js"), "trash_build")

    def test_zip_archive_analysis(self):
        res = super_media_tool.analyze_archive_structure(self.zip_path)
        self.assertGreater(res["total_files"], 0)
        self.assertEqual(res["blueprint"]["project_name"], "super-media-app")
        self.assertIn("React/Next.js", res["blueprint"]["detected_stack"])
        self.assertIn("TypeScript", res["blueprint"]["detected_stack"])
        self.assertGreaterEqual(res["breakdown"]["docs"]["count"], 2)
        self.assertGreaterEqual(res["breakdown"]["config"]["count"], 2)
        self.assertGreaterEqual(res["breakdown"]["code"]["count"], 2)

        md = super_media_tool.generate_archive_markdown_table(res)
        self.assertIn("Smart Categorized Archive Blueprint", md)
        self.assertIn("super-media-app", md)

    def test_tar_archive_analysis(self):
        res = super_media_tool.analyze_archive_structure(self.tar_path)
        self.assertGreater(res["total_files"], 0)
        self.assertIn("FastAPI", res["blueprint"]["detected_stack"])
        self.assertGreaterEqual(res["breakdown"]["code"]["count"], 1)


class TestSuperMediaCLIRunners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work_dir = setup_temp_dir()
        cls.video_path = os.path.join(cls.work_dir, "test_vid.mp4")
        cls.zip_path = os.path.join(cls.work_dir, "test_pkg.zip")
        create_synthetic_video(cls.video_path, duration=2)
        create_synthetic_zip(cls.zip_path)

    @classmethod
    def tearDownClass(cls):
        cleanup_temp_dir()

    def test_run_super_archive_json_and_table(self):
        class MockArgs:
            path = self.zip_path
            format = "json"
            compact = False

        with patch("agy_tools.modules.super_media_tool.emit_result") as mock_emit:
            super_media_tool.run_super_archive(MockArgs())
            self.assertTrue(mock_emit.called)
            args, kwargs = mock_emit.call_args
            data = args[0]
            self.assertEqual(data["blueprint"]["project_name"], "super-media-app")

    def test_run_super_video_reducer_pipeline(self):
        class MockArgs:
            path = self.video_path
            interval = "1s"
            threshold = 0.12
            format = "json"
            compact = False
            max_frames = 10
            transcribe = False
            language = "uz-UZ"
            output_dir = os.path.join(self.work_dir, "out_video")

        with patch("agy_tools.modules.super_media_tool.emit_result") as mock_emit:
            super_media_tool.run_super_video(MockArgs())
            self.assertTrue(mock_emit.called)
            args, kwargs = mock_emit.call_args
            data = args[0]
            self.assertIn("reduction_summary", data)
            self.assertIn("timeline_events", data)

    def test_run_super_pipeline_auto_dispatch(self):
        class MockArgsVideo:
            path = self.video_path
            interval = "1s"
            threshold = 0.12
            format = "json"
            compact = True
            max_frames = 5
            transcribe = False
            language = "uz-UZ"
            output_dir = os.path.join(self.work_dir, "out_pipe_vid")

        class MockArgsZip:
            path = self.zip_path
            format = "table"
            compact = True

        with patch("agy_tools.modules.super_media_tool.emit_result") as mock_emit:
            super_media_tool.run_super_pipeline(MockArgsVideo())
            self.assertTrue(mock_emit.called)

        with patch("agy_tools.modules.super_media_tool.emit_result") as mock_emit:
            super_media_tool.run_super_pipeline(MockArgsZip())
            self.assertTrue(mock_emit.called)

    def test_safe_jail_path_restriction(self):
        class MockUnsafeArgs:
            path = "/etc/shadow"
            format = "json"

        with self.assertRaises(PermissionError):
            safe_jail_path("/etc/shadow")


if __name__ == "__main__":
    unittest.main()
