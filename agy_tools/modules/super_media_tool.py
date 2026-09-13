import os
import sys
import re
import json
import math
import shutil
import base64
import tarfile
import zipfile
import subprocess
from pathlib import Path
from collections import Counter

from PIL import Image

from agy_tools.utils import emit_progress, emit_result, safe_jail_path
from agy_tools.modules import media_tool


DEFAULT_SUPER_MEDIA_DIR = "/home/fayzillo/Desktop/temp/super_media_artifacts"


def get_super_media_describe():
    """Returns the JSON schema and capabilities description of the super-media module."""
    return {
        "name": "super-media",
        "description": "Super Media Toolsuite: Video Intelligent Reducer & Timeline Sync, Smart Categorized Archive Pipeline va 0-Token Multimodal Digest.",
        "commands": {
            "video": "Videoni perceptual dHash orqali deyarli bir xil kadrlardan tozalash (<12%), audioni ajratish va STT timestamps bilan Audio-Visual Timeline jadvaliga sinxronlashtirish",
            "archive": "ZIP/TAR arxivini ochmasdan 5 toifaga (Docs, Config, Code, Media, Build/Trash) ajratish, loyiha arxitekturasini prioritetli tahlil qilish va 0-token xulosa berish",
            "pipeline": "Multimodal media quvuri (Video timeline sync, Archive categorized blueprint, Audio, Image yoki Matn avtomatik tahlili)"
        },
        "flags": {
            "--interval": "Kadrlar olish oralig'i (masalan '1s', '0.5s', '2')",
            "--threshold": "Perceptual dHash farq chegarasi (default: 0.12 ya'ni 12%)",
            "--compact": "Qisqartirilgan va ixcham 0-token hisoboti",
            "--format": "Chiqish formati: json yoki table (default: json)",
            "--language": "Nutqni aniqlash tili (default: uz-UZ, fallback: en-US)",
            "--no-transcribe": "Nutq transkripsiyasini (STT) o'chirish",
            "--max-frames": "Dastlab olinadigan maksimal kadrlar soni (default: 100)",
            "--output-dir": "Natijalar va artefaktlar saqlanadigan papka"
        }
    }


def ensure_super_media_output_dir(output_dir: str = None) -> str:
    """Creates and returns a verified safe directory for super media artifacts."""
    target_dir = output_dir or DEFAULT_SUPER_MEDIA_DIR
    target_dir = os.path.realpath(os.path.abspath(os.path.expanduser(target_dir)))
    safe_jail_path(target_dir)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


# ============================================================================
# 1. PERCEPTUAL DHASH & HAMMING DISTANCE REDUCER
# ============================================================================

def compute_image_dhash(img_or_path) -> str:
    """Computes 64-bit difference hash (dHash) from PIL Image or file path."""
    try:
        if isinstance(img_or_path, str):
            if not os.path.exists(img_or_path):
                return "0000000000000000"
            img = Image.open(img_or_path)
        else:
            img = img_or_path

        small = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS)
        pixels = list(small.getdata())
        diff = []
        for row in range(8):
            for col in range(8):
                idx = row * 9 + col
                diff.append(pixels[idx] > pixels[idx + 1])
        
        decimal_val = 0
        for bit in diff:
            decimal_val = (decimal_val << 1) | (1 if bit else 0)
        return f"{decimal_val:016x}"
    except Exception:
        return "0000000000000000"


def hamming_distance(hash1: str, hash2: str) -> int:
    """Computes bitwise Hamming distance between two 16-hex char (64-bit) hashes."""
    try:
        val1 = int(hash1, 16)
        val2 = int(hash2, 16)
        xor_val = val1 ^ val2
        return bin(xor_val).count('1')
    except Exception:
        return 64


def dhash_difference_ratio(hash1: str, hash2: str) -> float:
    """Returns the normalized difference ratio between 0.0 (identical) and 1.0 (completely opposite)."""
    dist = hamming_distance(hash1, hash2)
    return round(dist / 64.0, 4)


def reduce_frames_by_dhash(raw_frames: list, threshold: float = 0.12, keep_files: bool = True) -> list:
    """
    Filters out near-duplicate frames where perceptual difference < threshold (e.g. 12%).
    Returns a list of unique keyframe dictionaries with time duration and scene range.
    """
    if not raw_frames:
        return []

    unique_keyframes = []
    current_keyframe = None
    deleted_frames_count = 0

    for idx, f in enumerate(raw_frames):
        frame_path = f.get("path")
        frame_sec = f.get("timestamp_sec", idx * 1.0)
        
        f_hash = f.get("dhash")
        if not f_hash and frame_path and os.path.exists(frame_path):
            f_hash = compute_image_dhash(frame_path)
            f["dhash"] = f_hash

        if current_keyframe is None:
            # First keyframe
            current_keyframe = {
                "keyframe_id": 1,
                "frame_index": idx,
                "path": frame_path,
                "filename": os.path.basename(frame_path) if frame_path else f"frame_{idx:04d}.jpg",
                "timestamp_sec": frame_sec,
                "time_formatted": format_seconds(frame_sec),
                "duration_sec": 1.0,
                "dhash": f_hash,
                "merged_frames_count": 1,
                "end_timestamp_sec": frame_sec + 1.0,
                "end_time_formatted": format_seconds(frame_sec + 1.0)
            }
            unique_keyframes.append(current_keyframe)
        else:
            diff_ratio = dhash_difference_ratio(current_keyframe["dhash"], f_hash)
            if diff_ratio < threshold:
                # Near-duplicate frame (<12% diff) -> Merge into current keyframe
                current_keyframe["merged_frames_count"] += 1
                current_keyframe["end_timestamp_sec"] = frame_sec + 1.0
                current_keyframe["duration_sec"] = round(current_keyframe["end_timestamp_sec"] - current_keyframe["timestamp_sec"], 2)
                current_keyframe["end_time_formatted"] = format_seconds(current_keyframe["end_timestamp_sec"])
                
                # Delete duplicate frame file to save disk space if requested
                if not keep_files and frame_path and os.path.exists(frame_path) and frame_path != current_keyframe["path"]:
                    try:
                        os.remove(frame_path)
                    except Exception:
                        pass
                deleted_frames_count += 1
            else:
                # Significant scene change (>= 12% diff) -> New unique keyframe
                current_keyframe = {
                    "keyframe_id": len(unique_keyframes) + 1,
                    "frame_index": idx,
                    "path": frame_path,
                    "filename": os.path.basename(frame_path) if frame_path else f"frame_{idx:04d}.jpg",
                    "timestamp_sec": frame_sec,
                    "time_formatted": format_seconds(frame_sec),
                    "duration_sec": 1.0,
                    "dhash": f_hash,
                    "merged_frames_count": 1,
                    "difference_from_prev": diff_ratio,
                    "end_timestamp_sec": frame_sec + 1.0,
                    "end_time_formatted": format_seconds(frame_sec + 1.0)
                }
                unique_keyframes.append(current_keyframe)

    return unique_keyframes


def format_seconds(seconds: float) -> str:
    """Formats float/int seconds into [MM:SS] or [HH:MM:SS]."""
    secs = int(seconds)
    hrs = secs // 3600
    mins = (secs % 3600) // 60
    s = secs % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{s:02d}"
    return f"{mins:02d}:{s:02d}"


# ============================================================================
# 2. AUDIO-VISUAL TIMELINE SYNC ENGINE
# ============================================================================

def build_audio_visual_timeline(keyframes: list, audio_segments: list, video_duration: float = 0.0) -> list:
    """
    Synchronizes visual keyframes and audio speech segments onto a unified timeline table.
    Produces clean structured rows matching timestamps [MM:SS].
    """
    timeline_events = []
    
    # Map audio segments by time overlap
    # Keyframe: {timestamp_sec, end_timestamp_sec, path, dhash, ...}
    # AudioSegment: {start_seconds, end_seconds, time_range, text}
    
    for kf in keyframes:
        k_start = kf["timestamp_sec"]
        k_end = kf["end_timestamp_sec"]
        
        # Find overlapping speech segments
        matched_texts = []
        for seg in audio_segments:
            s_start = seg.get("start_seconds", 0.0)
            s_end = seg.get("end_seconds", s_start + 5.0)
            text = seg.get("text", "").strip()
            
            # Check overlap
            if not (k_end <= s_start or k_start >= s_end):
                if text:
                    matched_texts.append(text)
        
        speech_dialogue = " ".join(matched_texts) if matched_texts else "(Musiqa / Fon ovozi yoki nutqsiz kadr)"
        
        event = {
            "time_range": f"[{kf['time_formatted']} - {kf['end_time_formatted']}]",
            "start_sec": k_start,
            "end_sec": k_end,
            "keyframe_id": kf["keyframe_id"],
            "frame_file": kf["filename"],
            "frame_path": kf.get("path", ""),
            "dhash": kf.get("dhash", ""),
            "speech_transcript": speech_dialogue,
            "merged_frames": kf.get("merged_frames_count", 1),
            "visual_summary": f"Keyframe #{kf['keyframe_id']} ({kf.get('merged_frames_count', 1)} kadr birlashtirildi, dHash: {kf.get('dhash','')[:8]}...)"
        }
        timeline_events.append(event)

    # If no keyframes but audio segments exist
    if not timeline_events and audio_segments:
        for seg in audio_segments:
            s_start = seg.get("start_seconds", 0.0)
            s_end = seg.get("end_seconds", s_start + 5.0)
            text = seg.get("text", "").strip()
            timeline_events.append({
                "time_range": f"[{format_seconds(s_start)} - {format_seconds(s_end)}]",
                "start_sec": s_start,
                "end_sec": s_end,
                "keyframe_id": 0,
                "frame_file": "no_visual",
                "frame_path": "",
                "dhash": "",
                "speech_transcript": text or "(Jimlik)",
                "merged_frames": 0,
                "visual_summary": "Faqat Audio segment"
            })

    return timeline_events


def generate_timeline_markdown_table(timeline_events: list, video_meta: dict = None) -> str:
    """Generates an ultra-compact (~300 token) Audio-Visual Timeline Digest table in Markdown."""
    lines = []
    if video_meta:
        lines.append(f"### 🎬 Audio-Visual Timeline Digest ({video_meta.get('duration_formatted', '00:00')}, {video_meta.get('resolution', {}).get('width', 0)}x{video_meta.get('resolution', {}).get('height', 0)})")
    else:
        lines.append("### 🎬 Audio-Visual Timeline Digest")
    lines.append("")
    lines.append("| Vaqt Oralig'i | Vizual Kalit Kadr | Ovoz / Nutq Matni (STT) | Holat / Xulosa |")
    lines.append("|:---|:---|:---|:---|")
    
    for ev in timeline_events:
        time_col = ev["time_range"]
        vis_col = f"`{ev['frame_file']}` (id: {ev['keyframe_id']})" if ev["frame_file"] != "no_visual" else "—"
        audio_col = ev["speech_transcript"].replace("\n", " ").replace("|", "\\|")
        if len(audio_col) > 80:
            audio_col = audio_col[:77] + "..."
        summary_col = f"{ev['merged_frames']} kadr qisqartirildi" if ev['merged_frames'] > 1 else "Bitta kadr"
        lines.append(f"| {time_col} | {vis_col} | {audio_col} | {summary_col} |")

    return "\n".join(lines)


# ============================================================================
# 3. SMART CATEGORIZED ARCHIVE PIPELINE (0-TOKEN BLUEPRINT)
# ============================================================================

CATEGORIES = {
    "docs": {
        "name": "Hujjatlar (Documentation)",
        "patterns": [
            r"^readme(\..*)?$", r"^license(\..*)?$", r"^contributing(\..*)?$",
            r"^changelog(\..*)?$", r"^docs?/.*", r".*\.md$", r".*\.rst$",
            r".*\.txt$", r".*\.pdf$", r".*\.docx?$"
        ]
    },
    "config": {
        "name": "Konfiguratsiya (Configuration)",
        "patterns": [
            r"^package\.json$", r"^tsconfig(\..*)?\.json$", r"^dockerfile.*",
            r"^docker-compose.*\.ya?ml$", r"^requirements.*\.txt$", r"^pyproject\.toml$",
            r"^setup\.py$", r"^cargo\.toml$", r"^go\.mod$", r"^go\.sum$",
            r"^pom\.xml$", r"^build\.gradle.*", r"^\.env.*", r"^makefile$",
            r".*\.ya?ml$", r".*\.toml$", r".*\.ini$", r".*\.conf$", r".*\.config\..*"
        ]
    },
    "code": {
        "name": "Kodlar (Source Codes)",
        "patterns": [
            r"^(src|lib|app|routes|controllers|models|views|components|services|utils|pkg|api)/.*",
            r".*\.py$", r".*\.ts$", r".*\.js$", r".*\.go$", r".*\.rs$", r".*\.java$",
            r".*\.cpp$", r".*\.c$", r".*\.h$", r".*\.php$", r".*\.rb$", r".*\.html$",
            r".*\.css$", r".*\.scss$", r".*\.vue$", r".*\.jsx$", r".*\.tsx$",
            r".*\.sql$", r".*\.sh$"
        ]
    },
    "media": {
        "name": "Media (Media Assets)",
        "patterns": [
            r".*\.png$", r".*\.jpe?g$", r".*\.gif$", r".*\.svg$", r".*\.webp$",
            r".*\.ico$", r".*\.bmp$", r".*\.mp3$", r".*\.wav$", r".*\.ogg$",
            r".*\.mp4$", r".*\.mov$", r".*\.avi$", r".*\.mkv$", r".*\.ttf$",
            r".*\.woff2?$"
        ]
    },
    "trash_build": {
        "name": "Build/Trash (Build & Dependencies/Trash)",
        "patterns": [
            r"^node_modules/.*", r"^\.git/.*", r"^dist/.*", r"^build/.*",
            r"^__pycache__/.*", r".*\.pyc$", r"^\.next/.*", r"^target/.*",
            r"^vendor/.*", r"^\.cache/.*", r".*\.lock$", r"^package-lock\.json$",
            r"^yarn\.lock$", r"^pnpm-lock\.yaml$", r"^poetry\.lock$", r"^coverage/.*"
        ]
    }
}


def match_file_category(rel_path: str) -> str:
    """Categorizes a relative file path inside an archive into one of 5 standard categories."""
    clean_path = rel_path.strip("/").lower()
    base_name = os.path.basename(clean_path)

    # 1. Check trash_build first
    for pat in CATEGORIES["trash_build"]["patterns"]:
        if re.search(pat, clean_path) or re.search(pat, base_name):
            return "trash_build"

    # 2. Check config
    for pat in CATEGORIES["config"]["patterns"]:
        if re.search(pat, clean_path) or re.search(pat, base_name):
            return "config"

    # 3. Check docs
    for pat in CATEGORIES["docs"]["patterns"]:
        if re.search(pat, clean_path) or re.search(pat, base_name):
            return "docs"

    # 4. Check media
    for pat in CATEGORIES["media"]["patterns"]:
        if re.search(pat, clean_path) or re.search(pat, base_name):
            return "media"

    # 5. Check code
    for pat in CATEGORIES["code"]["patterns"]:
        if re.search(pat, clean_path) or re.search(pat, base_name):
            return "code"

    return "code" if any(clean_path.endswith(ext) for ext in [".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp"]) else "docs"


def analyze_archive_structure(archive_path: str) -> dict:
    """
    Analyzes ZIP or TAR archive safely in-memory, categorizing all files
    and parsing key metadata (package.json, pyproject.toml, README) for 0-token blueprint.
    """
    ext = os.path.splitext(archive_path)[1].lower()
    is_tar = archive_path.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"))
    is_zip = archive_path.endswith(".zip")

    if not is_tar and not is_zip:
        raise ValueError(f"Qo'llab-quvvatlanmaydigan arxiv formati: {archive_path}")

    categorized = {
        "docs": [],
        "config": [],
        "code": [],
        "media": [],
        "trash_build": []
    }

    total_files = 0
    total_uncompressed_bytes = 0
    key_files_content = {}
    directories = set()

    if is_zip:
        with zipfile.ZipFile(archive_path, "r") as zf:
            infolist = zf.infolist()
            for info in infolist:
                if info.is_dir():
                    directories.add(info.filename.rstrip("/"))
                    continue
                total_files += 1
                total_uncompressed_bytes += info.file_size
                cat = match_file_category(info.filename)
                categorized[cat].append({
                    "path": info.filename,
                    "size_bytes": info.file_size
                })
                
                # In-memory inspect key descriptor files
                lower_name = os.path.basename(info.filename).lower()
                if lower_name in ["package.json", "pyproject.toml", "cargo.toml", "go.mod", "dockerfile", "requirements.txt", "readme.md"]:
                    if info.file_size < 100 * 1024:  # <100KB
                        try:
                            key_files_content[lower_name] = zf.read(info.filename).decode("utf-8", errors="replace")
                        except Exception:
                            pass

    elif is_tar:
        with tarfile.open(archive_path, "r:*") as tf:
            for member in tf.getmembers():
                if member.isdir():
                    directories.add(member.name.rstrip("/"))
                    continue
                total_files += 1
                total_uncompressed_bytes += member.size
                cat = match_file_category(member.name)
                categorized[cat].append({
                    "path": member.name,
                    "size_bytes": member.size
                })
                
                lower_name = os.path.basename(member.name).lower()
                if lower_name in ["package.json", "pyproject.toml", "cargo.toml", "go.mod", "dockerfile", "requirements.txt", "readme.md"]:
                    if member.size < 100 * 1024:
                        try:
                            f = tf.extractfile(member)
                            if f:
                                key_files_content[lower_name] = f.read().decode("utf-8", errors="replace")
                        except Exception:
                            pass

    # Extract High-Level Architecture & Tech Stack (0-Token Blueprint)
    detected_stack = []
    project_name = Path(archive_path).stem
    project_description = ""
    entrypoints = []

    # 1. Package.json
    if "package.json" in key_files_content:
        try:
            pj = json.loads(key_files_content["package.json"])
            project_name = pj.get("name", project_name)
            project_description = pj.get("description", "")
            if pj.get("main"):
                entrypoints.append(pj["main"])
            deps = list(pj.get("dependencies", {}).keys()) + list(pj.get("devDependencies", {}).keys())
            if "react" in deps or "next" in deps:
                detected_stack.append("React/Next.js")
            if "vue" in deps or "nuxt" in deps:
                detected_stack.append("Vue/Nuxt")
            if "express" in deps or "fastify" in deps or "nestjs" in deps:
                detected_stack.append("Node.js Backend")
            if "typescript" in deps or any(f["path"].endswith(".ts") for f in categorized["code"]):
                detected_stack.append("TypeScript")
            else:
                detected_stack.append("JavaScript (Node.js)")
        except Exception:
            detected_stack.append("Node.js Project")

    # 2. Python (pyproject.toml / requirements.txt)
    if "pyproject.toml" in key_files_content or "requirements.txt" in key_files_content or any(f["path"].endswith(".py") for f in categorized["code"]):
        py_stack = ["Python"]
        reqs = key_files_content.get("requirements.txt", "") + key_files_content.get("pyproject.toml", "")
        if "fastapi" in reqs.lower():
            py_stack.append("FastAPI")
        elif "django" in reqs.lower():
            py_stack.append("Django")
        elif "flask" in reqs.lower():
            py_stack.append("Flask")
        detected_stack.extend(py_stack)

    # 3. Go
    if "go.mod" in key_files_content or any(f["path"].endswith(".go") for f in categorized["code"]):
        detected_stack.append("Go (Golang)")

    # 4. Rust
    if "cargo.toml" in key_files_content or any(f["path"].endswith(".rs") for f in categorized["code"]):
        detected_stack.append("Rust (Cargo)")

    # 5. Docker
    if "dockerfile" in key_files_content:
        detected_stack.append("Docker Containerized")

    # Clean stack
    detected_stack = list(dict.fromkeys(detected_stack)) or ["General Multi-Language Project"]

    # Readme title / summary if no description
    if not project_description and "readme.md" in key_files_content:
        first_lines = [l.strip("#* -") for l in key_files_content["readme.md"].splitlines() if l.strip()][:3]
        if first_lines:
            project_description = " - ".join(first_lines)

    # Breakdown statistics
    breakdown = {}
    for cat_key, cat_meta in CATEGORIES.items():
        files_in_cat = categorized[cat_key]
        size_sum = sum(f["size_bytes"] for f in files_in_cat)
        pct_files = round((len(files_in_cat) / max(1, total_files)) * 100, 1)
        breakdown[cat_key] = {
            "title": cat_meta["name"],
            "count": len(files_in_cat),
            "percent_files": pct_files,
            "size_bytes": size_sum,
            "sample_files": [f["path"] for f in files_in_cat[:5]]
        }

    return {
        "archive_path": archive_path,
        "archive_size_bytes": os.path.getsize(archive_path) if os.path.exists(archive_path) else 0,
        "total_files": total_files,
        "total_uncompressed_bytes": total_uncompressed_bytes,
        "blueprint": {
            "project_name": project_name,
            "detected_stack": detected_stack,
            "primary_stack": " / ".join(detected_stack),
            "description": project_description or "Tavsif mavjud emas",
            "entrypoints": entrypoints,
            "directories_count": len(directories)
        },
        "breakdown": breakdown,
        "categorized_files": categorized
    }


def generate_archive_markdown_table(archive_data: dict) -> str:
    """Formats categorized archive analysis into a clean Markdown table & Blueprint."""
    bp = archive_data["blueprint"]
    lines = []
    lines.append(f"### 📦 Smart Categorized Archive Blueprint: `{bp['project_name']}`")
    lines.append(f"**Texnologiyalar Stak:** `{bp['primary_stack']}`")
    if bp['description']:
        lines.append(f"**Tavsif:** {bp['description']}")
    lines.append(f"**Jami fayllar soni:** {archive_data['total_files']} ta | **Hajmi:** {archive_data['total_uncompressed_bytes']} bayt")
    lines.append("")
    lines.append("| Kategoriya | Fayllar Soni | Nisbati (%) | Hajmi (bayt) | Asosiy Fayllar Namunasi |")
    lines.append("|:---|:---|:---|:---|:---|")

    for cat_key, b in archive_data["breakdown"].items():
        samples = ", ".join([os.path.basename(p) for p in b["sample_files"][:3]]) or "—"
        lines.append(f"| **{b['title']}** | {b['count']} | {b['percent_files']}% | {b['size_bytes']} | `{samples}` |")

    return "\n".join(lines)


# ============================================================================
# 4. CLI RUNNERS: VIDEO, ARCHIVE, PIPELINE
# ============================================================================

def run_super_video(args):
    """Entrypoint for `agy-tool super-media video <path>`."""
    path = safe_jail_path(args.path)
    if not os.path.isfile(path):
        emit_result(None, success=False, error=f"Video fayl topilmadi: {path}")
        return

    emit_progress("Video Probe", 10, "Video metadata va parametrlari tahlil qilinmoqda...")
    meta = media_tool.probe_video_metadata(path)

    base_out = getattr(args, "output_dir", None)
    out_dir = ensure_super_media_output_dir(base_out)
    stem = Path(path).stem
    video_work_dir = os.path.join(out_dir, f"{stem}_super")
    os.makedirs(video_work_dir, exist_ok=True)

    interval_str = getattr(args, "interval", "1s") or "1s"
    try:
        interval = float(interval_str.rstrip("s"))
    except ValueError:
        interval = 1.0

    threshold = getattr(args, "threshold", 0.12)
    if threshold is None:
        threshold = 0.12
    threshold = float(threshold)

    max_frames = getattr(args, "max_frames", 100) or 100
    do_transcribe = getattr(args, "transcribe", True)
    language = getattr(args, "language", "uz-UZ") or "uz-UZ"
    out_format = getattr(args, "format", "json") or "json"
    compact = getattr(args, "compact", False)

    # 1. Extract frames
    emit_progress("Frames Extraction", 30, f"Har {interval}s da kadrlar ajratilmoqda...")
    raw_frames_dir = os.path.join(video_work_dir, "raw_frames")
    frames = media_tool.extract_video_frames(path, raw_frames_dir, interval=interval, max_frames=max_frames)

    # 2. Intelligent dHash Reducer (<12% duplicate filter)
    emit_progress("dHash Reducer", 50, f"Perceptual dHash orqali deyarli bir xil kadrlar filtrlanmoqda (<{int(threshold*100)}%)...")
    unique_keyframes = reduce_frames_by_dhash(frames, threshold=threshold, keep_files=False)

    # 3. Audio Extraction & Speech Chunking
    audio_segments = []
    if meta.get("has_audio"):
        emit_progress("Audio & STT", 70, "Videodan audio ajratilib, nutq vaqt bo'yicha transkripsiya qilinmoqda...")
        audio_out = os.path.join(video_work_dir, f"{stem}_audio.wav")
        audio_file = media_tool.extract_audio_from_video(path, audio_out)
        
        if audio_file and os.path.exists(audio_file):
            chunks_dir = os.path.join(video_work_dir, "audio_chunks")
            # 15-second chunks for finer alignment
            chunks = media_tool.chunk_and_clean_audio(audio_file, chunks_dir, chunk_size=15, silence_removal=False)
            
            if do_transcribe:
                for c in chunks:
                    txt = media_tool.transcribe_audio_segment(c["path"], language=language)
                    c["text"] = txt
                    audio_segments.append(c)
            else:
                for c in chunks:
                    c["text"] = "(Transkripsiya o'chirilgan)"
                    audio_segments.append(c)

    # 4. Synchronize Audio-Visual Timeline
    emit_progress("Timeline Sync", 90, "Audio va Vizual vaqt o'qi birlashtirilmoqda (Timeline Sync)...")
    timeline_events = build_audio_visual_timeline(unique_keyframes, audio_segments, meta.get("duration_seconds", 0.0))
    table_md = generate_timeline_markdown_table(timeline_events, meta)

    emit_progress("Complete", 100, "Super media video tahlili muvaffaqiyatli yakunlandi.")

    reduction_pct = round((1.0 - (len(unique_keyframes) / max(1, len(frames)))) * 100, 1) if frames else 0.0

    result = {
        "video_path": path,
        "metadata": meta,
        "reduction_summary": {
            "initial_frames_count": len(frames),
            "unique_keyframes_count": len(unique_keyframes),
            "reduction_percentage": f"{reduction_pct}%",
            "threshold": threshold
        },
        "timeline_events_count": len(timeline_events),
        "timeline_events": timeline_events if not compact else timeline_events[:15],
        "timeline_markdown_table": table_md
    }

    if out_format == "table":
        print(table_md)
    emit_result(result)


def run_super_archive(args):
    """Entrypoint for `agy-tool super-media archive <path>`."""
    path = safe_jail_path(args.path)
    if not os.path.isfile(path):
        emit_result(None, success=False, error=f"Arxiv fayl topilmadi: {path}")
        return

    emit_progress("Archive Inspection", 25, "Arxiv ichki tarkibi ochmasdan o'qilmoqda...")
    archive_data = analyze_archive_structure(path)

    emit_progress("Categorization & Blueprint", 75, "Fayllar 5 toifaga ajratilib, 0-token blueprint tuzilmoqda...")
    table_md = generate_archive_markdown_table(archive_data)

    emit_progress("Complete", 100, "Arxiv tahlili yakunlandi.")

    out_format = getattr(args, "format", "json") or "json"
    compact = getattr(args, "compact", False)

    if compact:
        archive_data["categorized_files"] = {k: len(v) for k, v in archive_data["categorized_files"].items()}

    archive_data["blueprint_markdown_table"] = table_md

    if out_format == "table":
        print(table_md)
    emit_result(archive_data)


def run_super_pipeline(args):
    """Entrypoint for `agy-tool super-media pipeline <path>`."""
    path = safe_jail_path(args.path)
    if not os.path.exists(path):
        emit_result(None, success=False, error=f"Fayl topilmadi: {path}")
        return

    ext = os.path.splitext(path)[1].lower()

    # If video
    if ext in [".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"]:
        run_super_video(args)
    # If archive
    elif ext in [".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz"]:
        run_super_archive(args)
    # Fallback to multimodal media pipeline
    else:
        media_tool.run_pipeline(args)
