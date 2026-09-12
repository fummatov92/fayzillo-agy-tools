import os
import sys
import re
import json
import math
import shutil
import base64
import struct
import tarfile
import zipfile
import subprocess
from pathlib import Path
from collections import Counter

from agy_tools.utils import emit_progress, emit_result, safe_jail_path


DEFAULT_TEMP_MEDIA_DIR = "/home/fayzillo/Desktop/temp/media_artifacts"


def get_media_describe():
    """Returns the JSON schema and capabilities description of the media module."""
    return {
        "name": "media",
        "description": "Interoperable Media Intelligence Toolsuite (Video, Audio, Image, Archive, Text va Multimodal Pipeline).",
        "commands": {
            "video": "Videoni tahlil qilish, metadata, kadrlarga ajratish (interval/keyframes/scene-change) va audio ajratish",
            "audio": "Audio metadata, 30 soniyalik qismlarga bo'lish, shovqin/jimlikni kesish va Speech-to-Text transkripsiya",
            "image": "Rasm tahlili (EXIF, Aspect Ratio, Perceptual dHash/aHash, Dominant Colors, ASCII grid va OCR)",
            "archive": "ZIP/TAR arxivlarini ochmasdan tahlil qilish, daraxt (Tree), xavfsizlik (Zip Bomb/Path Traversal) va ichki faylni o'qish",
            "text": "Markdown va hujjatlar strukturasi, bo'limlar xaritasi, 0-LLM token statistik tahlili va ixcham xulosa (Digest)",
            "pipeline": "Kompleks multimodal tahlil (Video/Audio/Image/Archive/Text dan yagona Multimodal Digest hisobotini yaratish)"
        },
        "flags": {
            "--interval": "Kadrlar ajratish oralig'i (masalan '5s', '2.5')",
            "--keyframes": "Faqat I-Frame (asosiy kadrlarni) ajratish",
            "--scene-change": "Sahna o'zgarishi (scene detection) bo'yicha kadrlarni ajratish",
            "--extract-audio": "Videodan audio trekni alohida WAV/MP3 formatda ajratib olish",
            "--chunk-size": "Audio segment hajmi soniyalarda (default: 30s)",
            "--silence-removal": "Audiodagi jimlikni kesib tashlash",
            "--transcribe": "Audio uchun Speech-to-Text transkripsiya yaratish",
            "--ocr": "Rasm ichidagi matnlarni OCR orqali aniqlash",
            "--palette-size": "Dominant ranglar soni (default: 5)",
            "--ascii-preview": "Terminal/AI uchun ASCII vizualizatsiya generatsiyasi",
            "--view-file": "Arxiv ichidagi faylni xotirada ochib o'qish",
            "--output-dir": "Natija va media artefaktlarni saqlash papkasi"
        }
    }


def ensure_media_output_dir(output_dir: str = None) -> str:
    """Creates and returns a verified safe directory for media artifacts inside ~/Desktop."""
    target_dir = output_dir or DEFAULT_TEMP_MEDIA_DIR
    target_dir = os.path.realpath(os.path.abspath(os.path.expanduser(target_dir)))
    safe_jail_path(target_dir)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


# ============================================================================
# 1. VIDEO INTELLIGENCE
# ============================================================================

def probe_video_metadata(video_path: str) -> dict:
    """Extracts rich video metadata using ffprobe with graceful fallback."""
    meta = {
        "format": os.path.splitext(video_path)[1].lstrip(".").lower(),
        "size_bytes": os.path.getsize(video_path) if os.path.exists(video_path) else 0,
        "duration_seconds": 0.0,
        "duration_formatted": "00:00:00",
        "fps": 0.0,
        "resolution": {"width": 0, "height": 0, "aspect_ratio": "unknown"},
        "video_codec": "unknown",
        "audio_codec": "unknown",
        "bitrate": 0,
        "has_audio": False,
        "streams_count": 0
    }

    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            video_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            fmt = data.get("format", {})
            meta["duration_seconds"] = round(float(fmt.get("duration", 0.0)), 2)
            meta["bitrate"] = int(fmt.get("bit_rate", 0))
            meta["size_bytes"] = int(fmt.get("size", meta["size_bytes"]))

            streams = data.get("streams", [])
            meta["streams_count"] = len(streams)

            for st in streams:
                codec_type = st.get("codec_type")
                if codec_type == "video" and meta["video_codec"] == "unknown":
                    meta["video_codec"] = st.get("codec_name", "unknown")
                    w = int(st.get("width", 0))
                    h = int(st.get("height", 0))
                    meta["resolution"]["width"] = w
                    meta["resolution"]["height"] = h
                    if w > 0 and h > 0:
                        gcd = math.gcd(w, h)
                        meta["resolution"]["aspect_ratio"] = f"{w // gcd}:{h // gcd}"

                    r_fps = st.get("r_frame_rate", "0/1")
                    if "/" in r_fps:
                        num, den = r_fps.split("/")
                        if float(den) > 0:
                            meta["fps"] = round(float(num) / float(den), 2)
                    elif r_fps:
                        meta["fps"] = round(float(r_fps), 2)

                elif codec_type == "audio":
                    meta["has_audio"] = True
                    if meta["audio_codec"] == "unknown":
                        meta["audio_codec"] = st.get("codec_name", "unknown")

            # Formatted duration
            secs = int(meta["duration_seconds"])
            hrs = secs // 3600
            mins = (secs % 3600) // 60
            s = secs % 60
            meta["duration_formatted"] = f"{hrs:02d}:{mins:02d}:{s:02d}"
    except Exception as e:
        meta["probe_error"] = str(e)

    return meta


def extract_video_frames(video_path: str, output_dir: str, interval: float = 5.0,
                         keyframes: bool = False, scene_change: float = None,
                         max_frames: int = 20) -> list:
    """Extracts keyframes or interval frames as JPEG images using ffmpeg."""
    os.makedirs(output_dir, exist_ok=True)
    frames_pattern = os.path.join(output_dir, "frame_%04d.jpg")

    cmd = ["ffmpeg", "-y", "-i", video_path]

    if keyframes:
        cmd += ["-vf", "select='eq(pict_type,I)'", "-vsync", "vfr"]
    elif scene_change is not None:
        threshold = scene_change if isinstance(scene_change, (int, float)) and scene_change > 0 else 0.3
        cmd += ["-vf", f"select='gt(scene,{threshold})'", "-vsync", "vfr"]
    else:
        # Interval mode
        interval_val = max(0.1, float(interval))
        fps_expr = f"fps=1/{interval_val}"
        cmd += ["-vf", fps_expr]

    cmd += ["-q:v", "2", "-frames:v", str(max_frames), frames_pattern]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception:
        pass

    # Collect extracted frames
    extracted = []
    for f in sorted(os.listdir(output_dir)):
        if f.startswith("frame_") and f.endswith(".jpg"):
            frame_path = os.path.join(output_dir, f)
            match = re.search(r"frame_(\d+)\.jpg", f)
            idx = int(match.group(1)) if match else len(extracted) + 1
            extracted.append({
                "frame_id": idx,
                "filename": f,
                "path": frame_path,
                "size_bytes": os.path.getsize(frame_path),
                "timestamp_approx": round((idx - 1) * float(interval if not keyframes else 2.0), 2)
            })

    return extracted


def extract_audio_from_video(video_path: str, output_path: str) -> str:
    """Extracts clean 16kHz mono WAV audio track from video."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        output_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode == 0 and os.path.exists(output_path):
            return output_path
    except Exception:
        pass
    return ""


def run_video(args):
    """Entrypoint for `agy-tool media video`."""
    path = safe_jail_path(args.path)
    if not os.path.isfile(path):
        emit_result(None, success=False, error=f"Video fayl topilmadi: {path}")
        return

    emit_progress("Video Metadata", 20, "Video parametrlari o'qilmoqda (ffprobe)...")
    meta = probe_video_metadata(path)

    # Determine frame extraction options
    interval_str = getattr(args, "interval", "5s") or "5s"
    interval = 5.0
    if isinstance(interval_str, str):
        cleaned = interval_str.lower().rstrip("s")
        try:
            interval = float(cleaned)
        except ValueError:
            interval = 5.0
    elif isinstance(interval_str, (int, float)):
        interval = float(interval_str)

    keyframes = getattr(args, "keyframes", False)
    scene_change = getattr(args, "scene_change", None)
    extract_audio_flag = getattr(args, "extract_audio", False)
    max_frames = getattr(args, "max_frames", 20) or 20

    base_out = getattr(args, "output_dir", None)
    out_dir = ensure_media_output_dir(base_out)
    video_stem = Path(path).stem
    frames_dir = os.path.join(out_dir, f"{video_stem}_frames")

    emit_progress("Frame Extraction", 50, f"Kadrlar ajratilmoqda (max: {max_frames})...")
    frames = extract_video_frames(
        path, frames_dir,
        interval=interval,
        keyframes=keyframes,
        scene_change=scene_change,
        max_frames=max_frames
    )

    audio_file = ""
    if extract_audio_flag or getattr(args, "pipeline_mode", False):
        emit_progress("Audio Extraction", 80, "Audio trek ajratib olinmoqda...")
        audio_out = os.path.join(out_dir, f"{video_stem}_audio.wav")
        audio_file = extract_audio_from_video(path, audio_out)

    emit_progress("Complete", 100, "Video tahlili yakunlandi.")

    result = {
        "file_path": path,
        "metadata": meta,
        "extraction": {
            "mode": "keyframes" if keyframes else ("scene-change" if scene_change else f"interval ({interval}s)"),
            "frames_count": len(frames),
            "frames_directory": frames_dir,
            "frames": frames[:10]  # Sample first 10 frames
        },
        "audio_extracted": audio_file if audio_file else None
    }
    emit_result(result)


# ============================================================================
# 2. AUDIO INTELLIGENCE & SPEECH-TO-TEXT
# ============================================================================

def probe_audio_metadata(audio_path: str) -> dict:
    """Extracts audio metadata using ffprobe with standard fallback."""
    meta = {
        "format": os.path.splitext(audio_path)[1].lstrip(".").lower(),
        "size_bytes": os.path.getsize(audio_path) if os.path.exists(audio_path) else 0,
        "duration_seconds": 0.0,
        "duration_formatted": "00:00:00",
        "sample_rate": 0,
        "channels": 1,
        "bitrate": 0,
        "codec": "unknown"
    }

    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            audio_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            fmt = data.get("format", {})
            meta["duration_seconds"] = round(float(fmt.get("duration", 0.0)), 2)
            meta["bitrate"] = int(fmt.get("bit_rate", 0))

            streams = data.get("streams", [])
            for st in streams:
                if st.get("codec_type") == "audio":
                    meta["codec"] = st.get("codec_name", "unknown")
                    meta["sample_rate"] = int(st.get("sample_rate", 0))
                    meta["channels"] = int(st.get("channels", 1))
                    break

            secs = int(meta["duration_seconds"])
            hrs = secs // 3600
            mins = (secs % 3600) // 60
            s = secs % 60
            meta["duration_formatted"] = f"{hrs:02d}:{mins:02d}:{s:02d}"
    except Exception as e:
        meta["probe_error"] = str(e)

    return meta


def chunk_and_clean_audio(audio_path: str, output_dir: str, chunk_size: int = 30,
                          silence_removal: bool = False) -> list:
    """Splits audio into uniform chunks and optionally trims leading/trailing silence."""
    os.makedirs(output_dir, exist_ok=True)
    chunk_pattern = os.path.join(output_dir, "chunk_%03d.wav")

    cmd = ["ffmpeg", "-y", "-i", audio_path]

    if silence_removal:
        cmd += [
            "-af",
            "silenceremove=start_periods=1:start_duration=0.5:start_threshold=-50dB:detection=peak"
        ]

    cmd += [
        "-f", "segment",
        "-segment_time", str(chunk_size),
        "-c:a", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        chunk_pattern
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception:
        pass

    chunks = []
    for f in sorted(os.listdir(output_dir)):
        if f.startswith("chunk_") and f.endswith(".wav"):
            cp = os.path.join(output_dir, f)
            match = re.search(r"chunk_(\d+)\.wav", f)
            idx = int(match.group(1)) if match else len(chunks)
            start_sec = idx * chunk_size
            end_sec = start_sec + chunk_size
            chunks.append({
                "chunk_id": idx + 1,
                "path": cp,
                "filename": f,
                "size_bytes": os.path.getsize(cp),
                "time_range": f"{start_sec//60:02d}:{start_sec%60:02d} - {end_sec//60:02d}:{end_sec%60:02d}",
                "start_seconds": start_sec,
                "end_seconds": end_sec
            })

    return chunks


def transcribe_audio_segment(wav_path: str, language: str = "uz-UZ") -> str:
    """Transcribes an audio chunk using speech_recognition or offline fallback."""
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = r.record(source)
            try:
                # Try google online recognizer
                text = r.recognize_google(audio_data, language=language)
                return text.strip()
            except Exception:
                pass
            # Try english fallback if uz fails or no internet
            if language != "en-US":
                try:
                    text = r.recognize_google(audio_data, language="en-US")
                    return text.strip()
                except Exception:
                    pass
    except Exception:
        pass
    return ""


def run_audio(args):
    """Entrypoint for `agy-tool media audio`."""
    path = safe_jail_path(args.path)
    if not os.path.isfile(path):
        emit_result(None, success=False, error=f"Audio fayl topilmadi: {path}")
        return

    emit_progress("Audio Metadata", 20, "Audio parametrlari o'qilmoqda...")
    meta = probe_audio_metadata(path)

    chunk_size = getattr(args, "chunk_size", 30) or 30
    silence_removal = getattr(args, "silence_removal", False)
    do_transcribe = getattr(args, "transcribe", True)
    language = getattr(args, "language", "uz-UZ") or "uz-UZ"

    base_out = getattr(args, "output_dir", None)
    out_dir = ensure_media_output_dir(base_out)
    audio_stem = Path(path).stem
    chunks_dir = os.path.join(out_dir, f"{audio_stem}_chunks")

    emit_progress("Audio Chunking", 50, f"Ovoz {chunk_size}s qismlarga bo'linmoqda...")
    chunks = chunk_and_clean_audio(path, chunks_dir, chunk_size=chunk_size, silence_removal=silence_removal)

    transcripts = []
    full_transcript_parts = []

    if do_transcribe and chunks:
        emit_progress("Speech-to-Text", 75, "Nutq matnga o'girilmoqda (STT)...")
        for c in chunks:
            txt = transcribe_audio_segment(c["path"], language=language)
            c["transcript"] = txt
            transcripts.append({
                "chunk_id": c["chunk_id"],
                "time_range": c["time_range"],
                "text": txt
            })
            if txt:
                full_transcript_parts.append(f"[{c['time_range']}] {txt}")

    emit_progress("Complete", 100, "Audio tahlili yakunlandi.")

    result = {
        "file_path": path,
        "metadata": meta,
        "chunking": {
            "chunk_size_sec": chunk_size,
            "chunks_count": len(chunks),
            "chunks_directory": chunks_dir,
            "silence_removal": silence_removal
        },
        "transcription": {
            "enabled": do_transcribe,
            "language": language,
            "full_transcript": "\n".join(full_transcript_parts) if full_transcript_parts else "",
            "segments": transcripts
        }
    }
    emit_result(result)


# ============================================================================
# 3. IMAGE INTELLIGENCE, PERCEPTUAL HASH, DOMINANT COLORS & OCR
# ============================================================================

NAMED_COLORS = [
    (0x00, 0x00, 0x00, "Black"),
    (0xFF, 0xFF, 0xFF, "White"),
    (0x80, 0x80, 0x80, "Gray"),
    (0xFF, 0x00, 0x00, "Red"),
    (0x00, 0xFF, 0x00, "Lime Green"),
    (0x00, 0x00, 0xFF, "Blue"),
    (0xFF, 0xFF, 0x00, "Yellow"),
    (0x00, 0xFF, 0xFF, "Cyan"),
    (0xFF, 0x00, 0xFF, "Magenta"),
    (0x80, 0x00, 0x00, "Maroon"),
    (0x00, 0x80, 0x00, "Dark Green"),
    (0x00, 0x00, 0x80, "Navy"),
    (0x80, 0x80, 0x00, "Olive"),
    (0x80, 0x00, 0x80, "Purple"),
    (0x00, 0x80, 0x80, "Teal"),
    (0xFF, 0xA5, 0x00, "Orange"),
    (0xA5, 0x2A, 0x2A, "Brown"),
    (0xFA, 0x80, 0x72, "Salmon"),
    (0x2E, 0x8B, 0x57, "Sea Green"),
    (0x46, 0x82, 0xB4, "Steel Blue"),
    (0x1F, 0x29, 0x37, "Dark Slate"),
    (0xF3, 0xF4, 0xF6, "Off White"),
]


def closest_color_name(r: int, g: int, b: int) -> str:
    """Finds nearest human-friendly color name based on Euclidean RGB distance."""
    best_dist = float("inf")
    best_name = "Custom"
    for cr, cg, cb, name in NAMED_COLORS:
        dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


def compute_dhash(img) -> str:
    """Computes 64-bit difference hash (dHash) for perceptual visual similarity."""
    try:
        # Resize to 9x8 and convert to grayscale
        small = img.convert("L").resize((9, 8))
        pixels = list(small.getdata())
        diff = []
        for row in range(8):
            for col in range(8):
                idx = row * 9 + col
                diff.append(pixels[idx] > pixels[idx + 1])
        # Convert 64 bits to 16 hex chars
        decimal_val = 0
        for bit in diff:
            decimal_val = (decimal_val << 1) | (1 if bit else 0)
        return f"{decimal_val:016x}"
    except Exception:
        return "0000000000000000"


def compute_ahash(img) -> str:
    """Computes 64-bit average hash (aHash)."""
    try:
        small = img.convert("L").resize((8, 8))
        pixels = list(small.getdata())
        avg = sum(pixels) / len(pixels)
        decimal_val = 0
        for p in pixels:
            decimal_val = (decimal_val << 1) | (1 if p >= avg else 0)
        return f"{decimal_val:016x}"
    except Exception:
        return "0000000000000000"


def extract_dominant_colors(img, count: int = 5) -> list:
    """Extracts dominant color palette with HEX codes, percentages and color names."""
    try:
        rgb_img = img.convert("RGB")
        # Resize for speed
        thumb = rgb_img.resize((100, 100))
        # Quantize image to palette
        quantized = thumb.quantize(colors=count, method=2)
        palette = quantized.getpalette()[:count * 3]
        
        # Count color frequency
        counts = Counter(quantized.getdata())
        total_pixels = sum(counts.values()) or 1

        palette_list = []
        for color_idx, freq in counts.most_common(count):
            r = palette[color_idx * 3]
            g = palette[color_idx * 3 + 1]
            b = palette[color_idx * 3 + 2]
            hex_code = f"#{r:02x}{g:02x}{b:02x}".upper()
            pct = round((freq / total_pixels) * 100, 1)
            palette_list.append({
                "hex": hex_code,
                "rgb": [r, g, b],
                "percent": pct,
                "name": closest_color_name(r, g, b)
            })
        return palette_list
    except Exception:
        return []


def generate_ascii_grid(img, width: int = 36, height: int = 14) -> str:
    """Generates compact ASCII representation of image for instant CLI/LLM visual preview."""
    chars = [" ", ".", ":", "-", "=", "+", "*", "#", "%", "@"]
    try:
        small = img.convert("L").resize((width, height))
        pixels = list(small.getdata())
        lines = []
        for y in range(height):
            row = []
            for x in range(width):
                val = pixels[y * width + x]
                idx = int((val / 255) * (len(chars) - 1))
                row.append(chars[idx])
            lines.append("".join(row))
        return "\n".join(lines)
    except Exception:
        return ""


def extract_ocr_text(image_path: str) -> dict:
    """Extracts text from image using tesseract or fallback layout detector."""
    ocr_result = {
        "text": "",
        "word_count": 0,
        "engine": "none",
        "has_text": False
    }

    # Try tesseract binary directly if available
    try:
        res = subprocess.run(
            ["tesseract", image_path, "stdout", "-l", "eng+uzb", "--psm", "3"],
            capture_output=True, text=True, timeout=10
        )
        if res.returncode == 0 and res.stdout.strip():
            text = res.stdout.strip()
            ocr_result["text"] = text
            ocr_result["word_count"] = len(text.split())
            ocr_result["engine"] = "tesseract-cli"
            ocr_result["has_text"] = True
            return ocr_result
    except Exception:
        pass

    # Try pytesseract python wrapper if present
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img).strip()
        if text:
            ocr_result["text"] = text
            ocr_result["word_count"] = len(text.split())
            ocr_result["engine"] = "pytesseract"
            ocr_result["has_text"] = True
            return ocr_result
    except Exception:
        pass

    return ocr_result


def analyze_image_file(image_path: str, palette_size: int = 5, include_ascii: bool = True,
                       include_base64: bool = False, run_ocr: bool = True) -> dict:
    """Performs deep image intelligence analysis."""
    from PIL import Image, ExifTags

    img = Image.open(image_path)
    w, h = img.size
    mode = img.mode
    img_format = img.format or os.path.splitext(image_path)[1].lstrip(".").upper()

    gcd = math.gcd(w, h)
    aspect_ratio = f"{w // gcd}:{h // gcd}" if gcd > 0 else "unknown"

    # EXIF Data Extraction
    exif_data = {}
    try:
        raw_exif = img._getexif()
        if raw_exif:
            for tag_id, val in raw_exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                # Skip raw binary buffers
                if isinstance(val, (bytes, bytearray)):
                    continue
                if tag_name not in ["MakerNote", "UserComment"]:
                    exif_data[str(tag_name)] = str(val)
    except Exception:
        pass

    dhash = compute_dhash(img)
    ahash = compute_ahash(img)
    palette = extract_dominant_colors(img, count=palette_size)
    ascii_art = generate_ascii_grid(img) if include_ascii else ""
    ocr_data = extract_ocr_text(image_path) if run_ocr else {"has_text": False, "text": ""}

    b64_uri = ""
    if include_base64:
        try:
            with open(image_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
                mime = f"image/{img_format.lower()}"
                b64_uri = f"data:{mime};base64,{encoded}"
        except Exception:
            pass

    return {
        "file_path": image_path,
        "dimensions": {
            "width": w,
            "height": h,
            "aspect_ratio": aspect_ratio,
            "megapixels": round((w * h) / 1_000_000, 2)
        },
        "format": img_format,
        "color_mode": mode,
        "size_bytes": os.path.getsize(image_path),
        "perceptual_hash": {
            "dhash": dhash,
            "ahash": ahash
        },
        "dominant_colors": palette,
        "ascii_preview": ascii_art,
        "ocr": ocr_data,
        "exif": exif_data,
        "base64_data_uri": b64_uri if b64_uri else None
    }


def run_image(args):
    """Entrypoint for `agy-tool media image`."""
    path = safe_jail_path(args.path)
    if not os.path.isfile(path):
        emit_result(None, success=False, error=f"Rasm fayli topilmadi: {path}")
        return

    emit_progress("Image Intelligence", 40, "Rasm metadatasi, ranglar va vizual xesh hisoblanmoqda...")
    palette_size = getattr(args, "palette_size", 5) or 5
    ascii_preview = getattr(args, "ascii_preview", True)
    include_base64 = getattr(args, "base64", False)
    run_ocr = getattr(args, "ocr", True)

    analysis = analyze_image_file(
        path,
        palette_size=palette_size,
        include_ascii=ascii_preview,
        include_base64=include_base64,
        run_ocr=run_ocr
    )

    emit_progress("Complete", 100, "Rasm tahlili yakunlandi.")
    emit_result(analysis)


# ============================================================================
# 4. ARCHIVE INTELLIGENCE & SECURITY AUDIT (ZIP / TAR)
# ============================================================================

def audit_and_inspect_archive(archive_path: str, view_file: str = None, max_depth: int = 5) -> dict:
    """Inspects ZIP/TAR archive contents, verifies safety (Zip Bomb / Path Traversal) and optionally reads a file."""
    ext = os.path.splitext(archive_path)[1].lower()
    is_tar = any(archive_path.lower().endswith(t) for t in [".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"])
    is_zip = archive_path.lower().endswith(".zip")

    compressed_size = os.path.getsize(archive_path)
    total_uncompressed_size = 0
    entries = []
    security_warnings = []
    is_safe = True

    viewed_content = None

    if is_zip:
        with zipfile.ZipFile(archive_path, "r") as zf:
            for info in zf.infolist():
                fname = info.filename
                fsize = info.file_size
                csize = info.compress_size
                total_uncompressed_size += fsize

                # Security check: Path traversal
                if fname.startswith("/") or fname.startswith("\\") or ".." in fname:
                    is_safe = False
                    security_warnings.append(f"Xavfli Path Traversal yo'li: '{fname}'")

                entries.append({
                    "path": fname,
                    "is_dir": info.is_dir(),
                    "size_bytes": fsize,
                    "compressed_size": csize
                })

                if view_file and (fname == view_file or fname.endswith("/" + view_file) or fname == view_file.lstrip("/")):
                    if fsize > 1_000_000:
                        viewed_content = "[XATO: Fayl hajmi 1MB dan katta, xotirada o'qish xavfsiz emas]"
                    else:
                        try:
                            viewed_content = zf.read(info).decode("utf-8", errors="replace")
                        except Exception as e:
                            viewed_content = f"[O'qishda xatolik: {str(e)}]"

    elif is_tar:
        mode = "r:*"
        with tarfile.open(archive_path, mode) as tf:
            for member in tf.getmembers():
                fname = member.name
                fsize = member.size
                total_uncompressed_size += fsize

                # Security check: Path traversal
                if fname.startswith("/") or fname.startswith("\\") or ".." in fname:
                    is_safe = False
                    security_warnings.append(f"Xavfli Path Traversal yo'li: '{fname}'")

                entries.append({
                    "path": fname,
                    "is_dir": member.isdir(),
                    "size_bytes": fsize,
                    "compressed_size": fsize  # tar members don't store per-file compressed size directly
                })

                if view_file and (fname == view_file or fname.endswith("/" + view_file) or fname == view_file.lstrip("/")):
                    if fsize > 1_000_000:
                        viewed_content = "[XATO: Fayl hajmi 1MB dan katta, xotirada o'qish xavfsiz emas]"
                    else:
                        try:
                            f = tf.extractfile(member)
                            if f:
                                viewed_content = f.read().decode("utf-8", errors="replace")
                        except Exception as e:
                            viewed_content = f"[O'qishda xatolik: {str(e)}]"
    else:
        raise ValueError(f"Qo'llab-quvvatlanmaydigan arxiv formati: {archive_path}")

    # Security check: Zip Bomb (compression ratio > 100:1 or total > 500MB from tiny archive)
    ratio = round(total_uncompressed_size / max(1, compressed_size), 2)
    if ratio > 100.0:
        is_safe = False
        security_warnings.append(f"Zip Bomb ehtimoli: Siqilish nisbati g'ayritabiiy yuqori ({ratio}:1)")
    if len(entries) > 10_000:
        security_warnings.append(f"Juda ko'p fayllar soni: {len(entries)} ta fayl")

    # Build Tree representation
    tree_lines = []
    dirs_count = sum(1 for e in entries if e["is_dir"])
    files_count = len(entries) - dirs_count

    for e in entries[:40]:  # Show top 40 entries in tree
        icon = "📁 " if e["is_dir"] else "📄 "
        tree_lines.append(f"{icon}{e['path']} ({e['size_bytes']} B)")
    if len(entries) > 40:
        tree_lines.append(f"... va yana {len(entries) - 40} ta fayl/jild")

    return {
        "file_path": archive_path,
        "format": "ZIP" if is_zip else "TAR",
        "archive_size_bytes": compressed_size,
        "uncompressed_size_bytes": total_uncompressed_size,
        "compression_ratio": f"{ratio}:1",
        "total_files": files_count,
        "total_directories": dirs_count,
        "security": {
            "is_safe": is_safe,
            "warnings": security_warnings
        },
        "tree_preview": "\n".join(tree_lines),
        "view_file": {
            "requested": view_file,
            "content": viewed_content
        } if view_file else None
    }


def run_archive(args):
    """Entrypoint for `agy-tool media archive`."""
    path = safe_jail_path(args.path)
    if not os.path.isfile(path):
        emit_result(None, success=False, error=f"Arxiv fayli topilmadi: {path}")
        return

    emit_progress("Archive Inspection", 40, "Arxiv xavfsizligi va strukturasi tekshirilmoqda...")
    view_file = getattr(args, "view_file", None)
    max_depth = getattr(args, "max_depth", 5) or 5

    res = audit_and_inspect_archive(path, view_file=view_file, max_depth=max_depth)
    emit_progress("Complete", 100, "Arxiv tahlili yakunlandi.")
    emit_result(res)


# ============================================================================
# 5. TEXT & MARKDOWN INTELLIGENCE (0-TOKEN EXTRACTIVE DIGEST)
# ============================================================================

STOP_WORDS = {
    # English
    "the", "and", "is", "in", "it", "of", "to", "for", "with", "on", "at", "by", "this", "that", "an", "as", "from",
    "be", "are", "was", "were", "or", "which", "into", "if", "then", "but", "about", "also", "all", "can", "will",
    # Uzbek
    "va", "bilan", "uchun", "ham", "bu", "shu", "kabi", "esa", "kerak", "bo'lib", "bo'lgan", "emas", "faqat", "yoki",
    "deb", "qilish", "qilingan", "o'z", "barcha", "bir", "har", "bunda", "orqali", "bo'yicha", "asosida", "lozim"
}


def analyze_markdown_structure(text: str) -> dict:
    """Extracts markdown structure: headings tree, code blocks, links, tables."""
    lines = text.splitlines()
    headings = []
    code_blocks = []
    links = []
    in_code_block = False
    current_code_lang = ""
    code_start_line = 0
    tables_count = 0

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Code blocks
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                current_code_lang = stripped.lstrip("`").strip()
                code_start_line = i
            else:
                in_code_block = False
                code_blocks.append({
                    "language": current_code_lang or "plain",
                    "start_line": code_start_line,
                    "end_line": i,
                    "line_count": i - code_start_line + 1
                })
            continue

        if in_code_block:
            continue

        # Headings (# H1, ## H2, etc)
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            headings.append({
                "level": level,
                "title": title,
                "line": i
            })

        # Table rows (| a | b |)
        if re.match(r"^\|(.+)\|$", stripped) and "---" in line:
            tables_count += 1

        # Markdown links [text](url)
        found_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", line)
        for link_text, link_url in found_links:
            links.append({"text": link_text, "url": link_url, "line": i})

    return {
        "headings": headings,
        "code_blocks": code_blocks,
        "links_count": len(links),
        "links_sample": links[:10],
        "tables_count": tables_count
    }


def compute_extractive_digest(text: str, top_keywords_count: int = 10, summary_sentences_count: int = 4) -> dict:
    """Computes pure algorithmic 0-token text digest, readability and extractive summary."""
    words = re.findall(r"\b[a-zA-Z\u0400-\u04FF']{2,}\b", text.lower())
    total_words = len(words)
    total_chars = len(text)
    lines = text.splitlines()

    # Filter stopwords and count frequencies
    filtered_words = [w for w in words if w not in STOP_WORDS]
    word_counts = Counter(filtered_words)
    top_keywords = [{"keyword": kw, "count": cnt} for kw, cnt in word_counts.most_common(top_keywords_count)]

    # Split into candidate sentences
    sentences = re.split(r"(?<=[.!?])\s+", text)
    scored_sentences = []

    keyword_set = {k["keyword"] for k in top_keywords}

    for idx, raw_s in enumerate(sentences):
        s = raw_s.strip()
        # Ignore code fences, very short or very long sentences
        if len(s) < 25 or len(s) > 300 or s.startswith("```") or s.startswith("#"):
            continue

        s_words = set(re.findall(r"\b[a-zA-Z\u0400-\u04FF']{2,}\b", s.lower()))
        overlap = len(s_words.intersection(keyword_set))
        # Position bonus (earlier sentences slightly prioritized)
        pos_score = 1.0 / (1.0 + idx * 0.05)
        score = overlap * 2.0 + pos_score

        scored_sentences.append((score, idx, s))

    scored_sentences.sort(key=lambda x: x[0], reverse=True)
    best_sentences = sorted(scored_sentences[:summary_sentences_count], key=lambda x: x[1])
    extractive_summary = " ".join(s[2] for s in best_sentences)

    # Reading time (average 200 words/min)
    reading_time_mins = max(1, math.ceil(total_words / 200)) if total_words > 0 else 0

    return {
        "metrics": {
            "characters_count": total_chars,
            "words_count": total_words,
            "lines_count": len(lines),
            "estimated_reading_time_minutes": reading_time_mins
        },
        "top_keywords": top_keywords,
        "extractive_summary": extractive_summary
    }


def analyze_text_document(file_path: str, top_keywords_count: int = 10) -> dict:
    """Extracts structure, statistical digest and summary for text/md/pdf/csv/json files."""
    ext = os.path.splitext(file_path)[1].lower()
    raw_content = ""

    if ext == ".pdf":
        # Safe extraction of basic text from PDF
        try:
            with open(file_path, "rb") as f:
                content_bytes = f.read()
                # Basic string stream extraction
                streams = re.findall(rb"stream[\r\n]+(.*?)[\r\n]+endstream", content_bytes, re.DOTALL)
                extracted_parts = []
                for st in streams[:10]:
                    try:
                        extracted_parts.append(st.decode("latin1", errors="ignore"))
                    except Exception:
                        pass
                raw_content = "\n".join(extracted_parts) if extracted_parts else "[PDF Binary Content]"
        except Exception as e:
            raw_content = f"[PDF o'qishda xato: {str(e)}]"
    else:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw_content = f.read()

    is_markdown = ext in [".md", ".markdown"]
    structure = analyze_markdown_structure(raw_content) if is_markdown else None
    digest = compute_extractive_digest(raw_content, top_keywords_count=top_keywords_count)

    return {
        "file_path": file_path,
        "format": ext.lstrip(".").upper(),
        "size_bytes": os.path.getsize(file_path),
        "structure": structure,
        "digest": digest
    }


def run_text(args):
    """Entrypoint for `agy-tool media text`."""
    path = safe_jail_path(args.path)
    if not os.path.isfile(path):
        emit_result(None, success=False, error=f"Hujjat fayli topilmadi: {path}")
        return

    emit_progress("Text Analysis", 40, "Matn statistikasi va strukturasi o'rganilmoqda...")
    keywords_count = getattr(args, "keywords", 10) or 10
    doc_res = analyze_text_document(path, top_keywords_count=keywords_count)

    emit_progress("Complete", 100, "Matn tahlili yakunlandi.")
    emit_result(doc_res)


# ============================================================================
# 6. MULTIMODAL MEDIA PIPELINE (UNIFIED INTELLIGENCE)
# ============================================================================

def auto_detect_media_type(file_path: str) -> str:
    """Infers media category from file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in [".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"]:
        return "video"
    elif ext in [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".wma"]:
        return "audio"
    elif ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".svg"]:
        return "image"
    elif ext in [".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"]:
        return "archive"
    elif ext in [".md", ".txt", ".json", ".csv", ".log", ".yaml", ".yml", ".pdf", ".html"]:
        return "text"
    return "unknown"


def run_pipeline(args):
    """Entrypoint for `agy-tool media pipeline` (Complete multimodal analysis)."""
    path = safe_jail_path(args.path)
    if not os.path.isfile(path):
        emit_result(None, success=False, error=f"Media fayl topilmadi: {path}")
        return

    media_type = auto_detect_media_type(path)
    base_out = getattr(args, "output_dir", None)
    out_dir = ensure_media_output_dir(base_out)
    stem = Path(path).stem

    multimodal_report = {
        "pipeline_target": path,
        "detected_type": media_type,
        "timestamp": os.environ.get("AGY_TIMESTAMP", "live"),
        "modules_executed": []
    }

    if media_type == "video":
        emit_progress("Pipeline: Video Metadata", 15, "Videodan metadata o'qilmoqda...")
        v_meta = probe_video_metadata(path)
        multimodal_report["video_metadata"] = v_meta
        multimodal_report["modules_executed"].append("video_metadata")

        # Extract frames
        emit_progress("Pipeline: Keyframe Extraction", 35, "Asosiy kadrlar ajratilmoqda...")
        frames_dir = os.path.join(out_dir, f"{stem}_pipeline_frames")
        frames = extract_video_frames(path, frames_dir, interval=5.0, max_frames=6)
        multimodal_report["frames_count"] = len(frames)
        multimodal_report["modules_executed"].append("frame_extraction")

        # Analyze extracted frames using image intelligence
        emit_progress("Pipeline: Visual Intelligence", 55, "Kadrlardagi ranglar va vizual tuzilma tahlil qilinmoqda...")
        frame_analyses = []
        for f_item in frames[:4]:
            try:
                f_res = analyze_image_file(f_item["path"], palette_size=3, include_ascii=False, run_ocr=True)
                frame_analyses.append({
                    "frame_id": f_item["frame_id"],
                    "timestamp": f_item["timestamp_approx"],
                    "dominant_colors": f_res["dominant_colors"],
                    "dhash": f_res["perceptual_hash"]["dhash"],
                    "ocr_text": f_res["ocr"]["text"]
                })
            except Exception:
                pass
        multimodal_report["frames_visual_digest"] = frame_analyses
        multimodal_report["modules_executed"].append("visual_ocr_intelligence")

        # Extract and transcribe audio
        if v_meta.get("has_audio"):
            emit_progress("Pipeline: Audio & Speech Extraction", 75, "Audio trek ajratilib, matnga o'girilmoqda...")
            audio_out = os.path.join(out_dir, f"{stem}_audio.wav")
            audio_path = extract_audio_from_video(path, audio_out)
            if audio_path and os.path.exists(audio_path):
                chunks_dir = os.path.join(out_dir, f"{stem}_pipeline_chunks")
                chunks = chunk_and_clean_audio(audio_path, chunks_dir, chunk_size=30)
                transcripts = []
                for c in chunks[:5]:
                    txt = transcribe_audio_segment(c["path"])
                    if txt:
                        transcripts.append(f"[{c['time_range']}]: {txt}")
                multimodal_report["audio_transcript"] = "\n".join(transcripts)
                multimodal_report["modules_executed"].append("speech_to_text")

    elif media_type == "audio":
        emit_progress("Pipeline: Audio Analysis", 30, "Audio tahlili...")
        a_meta = probe_audio_metadata(path)
        chunks_dir = os.path.join(out_dir, f"{stem}_pipeline_chunks")
        chunks = chunk_and_clean_audio(path, chunks_dir, chunk_size=30)
        transcripts = []
        for c in chunks:
            txt = transcribe_audio_segment(c["path"])
            if txt:
                transcripts.append(f"[{c['time_range']}]: {txt}")
        multimodal_report["audio_metadata"] = a_meta
        multimodal_report["transcript"] = "\n".join(transcripts)
        multimodal_report["modules_executed"].extend(["audio_metadata", "speech_to_text"])

    elif media_type == "image":
        emit_progress("Pipeline: Image Analysis", 40, "Rasm tahlili va OCR...")
        img_res = analyze_image_file(path, palette_size=5, include_ascii=True, run_ocr=True)
        multimodal_report["image_intelligence"] = img_res
        multimodal_report["modules_executed"].append("image_intelligence")

    elif media_type == "archive":
        emit_progress("Pipeline: Archive Inspection", 40, "Arxiv xavfsizlik va daraxt tekshiruvi...")
        arch_res = audit_and_inspect_archive(path, view_file="README.md")
        multimodal_report["archive_audit"] = arch_res
        multimodal_report["modules_executed"].append("archive_audit")

    elif media_type == "text":
        emit_progress("Pipeline: Text Intelligence", 40, "Matn statistikasi va digest...")
        txt_res = analyze_text_document(path)
        multimodal_report["text_digest"] = txt_res
        multimodal_report["modules_executed"].append("text_digest")

    else:
        emit_result(None, success=False, error=f"Noma'lum yoki qo'llab-quvvatlanmaydigan media fayl: {path}")
        return

    emit_progress("Complete", 100, "Multimodal pipeline yakunlandi.")
    emit_result(multimodal_report)
