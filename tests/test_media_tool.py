import os
import sys
import math
import shutil
import tempfile
import subprocess
import zipfile
import tarfile
import struct
import wave

# Ensure parent dir is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from PIL import Image, ImageDraw
from agy_tools.modules import media_tool
from agy_tools.utils import safe_jail_path


TEST_TEMP_DIR = os.path.join(parent_dir, "tests_temp_media")


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


def create_synthetic_audio(filepath: str, duration: int = 3):
    """Creates a small synthetic 16kHz mono WAV audio file."""
    with wave.open(filepath, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        # 1000Hz sine wave samples
        num_samples = 16000 * duration
        data = bytearray()
        for i in range(num_samples):
            val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * 440.0 * i / 16000.0))
            data.extend(struct.pack("<h", val))
        wav.writeframes(data)


def create_synthetic_image(filepath: str, width: int = 200, height: int = 150):
    """Creates a sample multi-colored PNG/JPEG image."""
    img = Image.new("RGB", (width, height), color=(255, 0, 0))  # Red base
    draw = ImageDraw.Draw(img)
    # Draw blue rectangle
    draw.rectangle([50, 30, 150, 100], fill=(0, 0, 255))
    # Draw green circle
    draw.ellipse([70, 40, 130, 90], fill=(0, 255, 0))
    img.save(filepath)


def test_video_intelligence():
    print("[TEST] Testing 1. media video (Metadata, Frame Extraction & Audio Track)...")
    work_dir = setup_temp_dir()
    video_path = os.path.join(work_dir, "sample_test_video.mp4")
    create_synthetic_video(video_path, duration=3)

    assert os.path.exists(video_path), "Synthetic video yaratilmadi!"

    # 1. Metadata check
    meta = media_tool.probe_video_metadata(video_path)
    assert meta["duration_seconds"] > 0, "Video duration noto'g'ri"
    assert meta["resolution"]["width"] == 320, "Video kengligi noto'g'ri"
    assert meta["resolution"]["height"] == 240, "Video balandligi noto'g'ri"
    assert meta["resolution"]["aspect_ratio"] == "4:3", f"Aspect ratio noto'g'ri: {meta['resolution']['aspect_ratio']}"
    assert meta["has_audio"] is True, "Video audio stream aniqlanmadi"
    assert meta["fps"] > 0, "Video FPS topilmadi"

    # 2. Frame extraction
    frames_dir = os.path.join(work_dir, "vid_frames")
    frames = media_tool.extract_video_frames(video_path, frames_dir, interval=1.0, max_frames=5)
    assert len(frames) > 0, "Kadrlar ajratilmadi"
    assert os.path.exists(frames[0]["path"]), "Ajratilgan kadr fayli mavjud emas"

    # 3. Audio extraction
    audio_out = os.path.join(work_dir, "extracted_audio.wav")
    audio_file = media_tool.extract_audio_from_video(video_path, audio_out)
    assert os.path.exists(audio_file), "Videodan audio ajratilmadi"
    assert os.path.getsize(audio_file) > 1000, "Ajratilgan audio hajmi juda kichik"

    print("  ✓ media video tests passed.")


def test_audio_intelligence():
    print("[TEST] Testing 2. media audio (Metadata, Chunking, Silence & STT)...")
    work_dir = setup_temp_dir()
    audio_path = os.path.join(work_dir, "sample_test_audio.wav")
    create_synthetic_audio(audio_path, duration=4)

    assert os.path.exists(audio_path), "Synthetic audio yaratilmadi!"

    # 1. Metadata probe
    meta = media_tool.probe_audio_metadata(audio_path)
    assert meta["sample_rate"] == 16000 or meta["duration_seconds"] > 0, "Audio metadata olinmadi"
    assert meta["channels"] in [1, 2], "Channels aniqlanmadi"

    # 2. Chunking
    chunks_dir = os.path.join(work_dir, "aud_chunks")
    chunks = media_tool.chunk_and_clean_audio(audio_path, chunks_dir, chunk_size=2)
    assert len(chunks) >= 2, f"Audio 2s qismlarga bo'linmadi: count={len(chunks)}"
    assert "time_range" in chunks[0], "Chunk time_range topilmadi"

    # 3. STT segment handler (graceful offline fallback)
    transcript = media_tool.transcribe_audio_segment(chunks[0]["path"])
    assert isinstance(transcript, str), "Transcript string bo'lishi kerak"

    print("  ✓ media audio tests passed.")


def test_image_intelligence():
    print("[TEST] Testing 3. media image (EXIF, dHash/aHash, Dominant Colors, ASCII & OCR)...")
    work_dir = setup_temp_dir()
    image_path = os.path.join(work_dir, "sample_test_image.png")
    create_synthetic_image(image_path, width=200, height=100)

    # 1. Full Image Analysis
    analysis = media_tool.analyze_image_file(image_path, palette_size=4, include_ascii=True, include_base64=True)

    assert analysis["dimensions"]["width"] == 200
    assert analysis["dimensions"]["height"] == 100
    assert analysis["dimensions"]["aspect_ratio"] == "2:1"

    # 2. Perceptual hashes
    dhash = analysis["perceptual_hash"]["dhash"]
    ahash = analysis["perceptual_hash"]["ahash"]
    assert len(dhash) == 16, f"dHash 16-hex belgidan iborat bo'lishi shart: {dhash}"
    assert len(ahash) == 16, f"aHash 16-hex belgidan iborat bo'lishi shart: {ahash}"

    # 3. Dominant colors
    palette = analysis["dominant_colors"]
    assert len(palette) > 0, "Dominant ranglar ajratilmadi"
    assert "hex" in palette[0] and "name" in palette[0] and "percent" in palette[0]

    # 4. ASCII preview
    ascii_art = analysis["ascii_preview"]
    assert len(ascii_art) > 50, "ASCII vizual grid yaratilmadi"
    assert "\n" in ascii_art

    # 5. Base64
    assert analysis["base64_data_uri"].startswith("data:image/")

    print("  ✓ media image tests passed.")


def test_archive_intelligence():
    print("[TEST] Testing 4. media archive (ZIP/TAR Tree, Security Zip-Bomb/Traversal & view-file)...")
    work_dir = setup_temp_dir()

    # 1. Create Normal ZIP
    zip_path = os.path.join(work_dir, "sample_normal.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("README.md", "# Test Project\nThis is a sample readme inside archive.")
        zf.writestr("src/main.py", "print('Hello from archive')\n")
        zf.writestr("config/app.json", '{"version": "1.0.0"}')

    res_zip = media_tool.audit_and_inspect_archive(zip_path, view_file="README.md")
    assert res_zip["format"] == "ZIP"
    assert res_zip["total_files"] == 3
    assert res_zip["security"]["is_safe"] is True
    assert "Test Project" in res_zip["view_file"]["content"]
    assert "src/main.py" in res_zip["tree_preview"]

    # 2. Create Path Traversal Malicious ZIP
    evil_zip_path = os.path.join(work_dir, "evil_traversal.zip")
    with zipfile.ZipFile(evil_zip_path, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0:root:/root:/bin/bash")

    res_evil = media_tool.audit_and_inspect_archive(evil_zip_path)
    assert res_evil["security"]["is_safe"] is False, "Path traversal xavfi aniqlanmadi!"
    assert any("Traversal" in w for w in res_evil["security"]["warnings"])

    # 3. Create Normal TAR.GZ
    tar_path = os.path.join(work_dir, "sample_normal.tar.gz")
    with tarfile.open(tar_path, "w:gz") as tf:
        data = b"# Tar Readme Content"
        ti = tarfile.TarInfo(name="README.md")
        ti.size = len(data)
        import io
        tf.addfile(ti, io.BytesIO(data))

    res_tar = media_tool.audit_and_inspect_archive(tar_path, view_file="README.md")
    assert res_tar["format"] == "TAR"
    assert res_tar["security"]["is_safe"] is True
    assert "Tar Readme Content" in res_tar["view_file"]["content"]

    print("  ✓ media archive tests passed.")


def test_text_and_markdown_intelligence():
    print("[TEST] Testing 5. media text (Markdown structure, Code blocks, 0-token Digest)...")
    work_dir = setup_temp_dir()
    md_path = os.path.join(work_dir, "sample_doc.md")

    md_content = """# Media Intelligence Architecture

JarvisOS Media Suite bu multimodal tahlil vositasi hisoblanadi.
U video, audio, image va arxivlarni tahlil qilish uchun mo'ljallangan.

## Modul Imkoniyatlari
Bu vosita orqali siz quyidagi imkoniyatlarga ega bo'lasiz:
- Video kadrlarni ajratish
- Audio nutqni matnga o'girish

```python
def process_video(path):
    print("Processing:", path)
```

### Qo'shimcha Havolalar
Batafsil ma'lumot uchun [Hujjatlar](https://example.com/docs) havolasiga qarang.

| Parametr | Qiymat |
|---|---|
| Timeout | 30s |
| Threads | 4 |

Ushbu loyiha orqali barcha multimodal operatsiyalar avtomatlashtiriladi va xavfsiz bajariladi.
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    doc_res = media_tool.analyze_text_document(md_path, top_keywords_count=5)

    assert doc_res["format"] == "MD"
    assert doc_res["structure"] is not None
    # Check headings
    headings = doc_res["structure"]["headings"]
    assert len(headings) == 3
    assert headings[0]["title"] == "Media Intelligence Architecture"
    assert headings[0]["level"] == 1
    assert headings[1]["title"] == "Modul Imkoniyatlari"
    assert headings[1]["level"] == 2

    # Check code blocks
    code_blocks = doc_res["structure"]["code_blocks"]
    assert len(code_blocks) == 1
    assert code_blocks[0]["language"] == "python"

    # Check links and tables
    assert doc_res["structure"]["links_count"] == 1
    assert doc_res["structure"]["tables_count"] == 1

    # Check 0-token digest
    digest = doc_res["digest"]
    assert digest["metrics"]["words_count"] > 10
    assert len(digest["top_keywords"]) > 0
    assert len(digest["extractive_summary"]) > 20

    print("  ✓ media text tests passed.")


def test_multimodal_pipeline():
    print("[TEST] Testing 6. media pipeline (Unified Multimodal Intelligence)...")
    work_dir = setup_temp_dir()

    # Test pipeline on video
    video_path = os.path.join(work_dir, "pipeline_video.mp4")
    create_synthetic_video(video_path, duration=3)

    class MockArgs:
        def __init__(self, path):
            self.path = path
            self.output_dir = os.path.join(work_dir, "pipeline_out")

    # Capture output via emit_result callback
    captured = {}
    from agy_tools.utils import set_result_hook
    set_result_hook(lambda d, s, e: captured.update({"data": d, "success": s, "error": e}))

    media_tool.run_pipeline(MockArgs(video_path))

    assert captured.get("success") is True, f"Pipeline xatosi: {captured.get('error')}"
    data = captured["data"]
    assert data["detected_type"] == "video"
    assert "video_metadata" in data
    assert "frames_visual_digest" in data
    assert "modules_executed" in data
    assert "video_metadata" in data["modules_executed"]

    # Test pipeline on image
    image_path = os.path.join(work_dir, "pipeline_image.png")
    create_synthetic_image(image_path)
    media_tool.run_pipeline(MockArgs(image_path))
    assert captured["data"]["detected_type"] == "image"
    assert "image_intelligence" in captured["data"]

    # Test pipeline on text
    text_path = os.path.join(work_dir, "pipeline_doc.md")
    with open(text_path, "w") as f:
        f.write("# Hello World\nPipeline document test.")
    media_tool.run_pipeline(MockArgs(text_path))
    assert captured["data"]["detected_type"] == "text"
    assert "text_digest" in captured["data"]

    print("  ✓ media pipeline tests passed.")


def test_cli_integration():
    print("[TEST] Testing CLI execution (`./bin/agy-tool media ...`)...")
    work_dir = setup_temp_dir()
    img_path = os.path.join(work_dir, "cli_img.png")
    create_synthetic_image(img_path)

    # 1. agy-tool media image
    res = subprocess.run(
        ["./bin/agy-tool", "media", "image", img_path],
        capture_output=True, text=True
    )
    assert res.returncode == 0, f"CLI media image xatosi: {res.stderr}"
    import json
    parsed = json.loads(res.stdout)
    assert parsed["success"] is True
    assert parsed["data"]["dimensions"]["width"] == 200

    # 2. agy-tool media describe
    res_desc = subprocess.run(
        ["./bin/agy-tool", "--describe"],
        capture_output=True, text=True
    )
    assert res_desc.returncode == 0
    desc_parsed = json.loads(res_desc.stdout)
    assert "media" in desc_parsed["data"]["modules"]
    assert "pipeline" in desc_parsed["data"]["modules"]["media"]["commands"]

    print("  ✓ CLI integration tests passed.")


def main():
    try:
        test_video_intelligence()
        test_audio_intelligence()
        test_image_intelligence()
        test_archive_intelligence()
        test_text_and_markdown_intelligence()
        test_multimodal_pipeline()
        test_cli_integration()
        print("\n🎉 ALL 6 MEDIA INTELLIGENCE TESTS PASSED SUCCESSFULLY!")
    finally:
        cleanup_temp_dir()


if __name__ == "__main__":
    main()
