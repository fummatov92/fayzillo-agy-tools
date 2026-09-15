import os
import zipfile
import tarfile
import fnmatch
from pathlib import Path
from agy_tools.utils import emit_progress, emit_result, safe_jail_path

DEFAULT_EXCLUDE_DIRS = {
    'node_modules', 'dist', 'build', '.git', '__pycache__', 
    '.pytest_cache', '.turbo', '.next', '.cache', 'target', 
    'coverage', '.venv', 'venv', '.idea', '.vscode'
}

DEFAULT_EXCLUDE_FILES = {
    '.env', '.env.local', '.env.production', '.env.staging',
    '*.pyc', '*.pyo', '*.pyd', '*.log', '*.tmp', '*.swp',
    '.DS_Store', 'Thumbs.db', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml'
}

CRITICAL_SECRET_PATTERNS = {
    '*.key', '*.pem', '*.crt', '*.cer', '*.p12', '*.pfx',
    'id_rsa*', 'id_ed25519*', '*_rsa', '*_ed25519',
    '.env', '.env.*', '*credential*', '*secret*'
}

def is_excluded(rel_path: str, is_dir: bool, custom_excludes: set = None, clean: bool = True) -> bool:
    norm_path = rel_path.replace('\\', '/')
    parts = norm_path.split('/')
    filename = parts[-1]

    if clean:
        # Check directory exclusions
        for part in parts[:-1] if not is_dir else parts:
            if part in DEFAULT_EXCLUDE_DIRS or part.startswith('.'):
                if part not in {'.', '..'}:
                    return True
        
        # Check file exclusions
        if not is_dir:
            if filename in DEFAULT_EXCLUDE_FILES:
                return True
            for pattern in DEFAULT_EXCLUDE_FILES:
                if fnmatch.fnmatch(filename, pattern):
                    return True
            for secret_pattern in CRITICAL_SECRET_PATTERNS:
                if fnmatch.fnmatch(filename.lower(), secret_pattern):
                    return True

    if custom_excludes:
        for excl in custom_excludes:
            excl_norm = excl.replace('\\', '/').strip()
            if not excl_norm:
                continue
            if fnmatch.fnmatch(norm_path, excl_norm) or fnmatch.fnmatch(filename, excl_norm):
                return True
            if any(fnmatch.fnmatch(p, excl_norm) for p in parts):
                return True

    return False

def pack_archive(source_dir: str, output_path: str = None, clean: bool = True, exclude: str = None) -> dict:
    """Packs a directory cleanly into a ZIP archive with smart exclusion and 0-secret safety."""
    emit_progress("Archive Validation", 10, "Manba jildi va xavfsizlik tekshirilmoqda...")
    safe_src = safe_jail_path(source_dir)
    if not os.path.exists(safe_src) or not os.path.isdir(safe_src):
        raise ValueError(f"Ko'rsatilgan manba katalogi mavjud emas: '{source_dir}'")

    src_name = os.path.basename(safe_src.rstrip('/\\')) or "archive"
    if not output_path:
        output_path = os.path.join(os.path.dirname(safe_src), f"{src_name}_clean.zip")
    
    safe_out = safe_jail_path(output_path, base_dir=os.path.dirname(safe_src))
    os.makedirs(os.path.dirname(safe_out), exist_ok=True)

    custom_excludes = set(p.strip() for p in exclude.split(',') if p.strip()) if exclude else set()

    emit_progress("Scanning Files", 30, "Fayllar saralanmoqda va maxfiyliklar filtrlanmoqda...")
    files_to_pack = []
    total_uncompressed = 0

    for root, dirs, files in os.walk(safe_src):
        rel_root = os.path.relpath(root, safe_src)
        if rel_root != '.' and is_excluded(rel_root, is_dir=True, custom_excludes=custom_excludes, clean=clean):
            dirs[:] = []
            continue

        for f in files:
            full_path = os.path.join(root, f)
            rel_file = os.path.relpath(full_path, safe_src)
            if is_excluded(rel_file, is_dir=False, custom_excludes=custom_excludes, clean=clean):
                continue
            sz = os.path.getsize(full_path)
            files_to_pack.append((full_path, rel_file.replace('\\', '/'), sz))
            total_uncompressed += sz

    emit_progress("Compressing", 60, f"{len(files_to_pack)} ta fayl siqilmoqda (ZIP_DEFLATED)...")
    with zipfile.ZipFile(safe_out, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for full_p, norm_rel_p, _ in files_to_pack:
            zipf.write(full_p, norm_rel_p)

    compressed_size = os.path.getsize(safe_out)
    ratio = round((1 - (compressed_size / (total_uncompressed or 1))) * 100, 1)

    emit_progress("Complete", 100, f"Arxiv yaratildi: {round(compressed_size/1024, 2)} KB")
    
    data = {
        "source_directory": safe_src,
        "archive_path": safe_out,
        "total_files": len(files_to_pack),
        "uncompressed_bytes": total_uncompressed,
        "compressed_bytes": compressed_size,
        "uncompressed_formatted": f"{round(total_uncompressed / 1024, 2)} KB",
        "compressed_formatted": f"{round(compressed_size / 1024, 2)} KB",
        "compression_ratio": f"{ratio}%",
        "clean_mode": clean,
        "custom_excludes": list(custom_excludes)
    }
    return emit_result(data, success=True)

def unpack_archive(archive_path: str, target_dir: str = None) -> dict:
    """Safely extracts an archive, normalizing cross-platform slashes and preventing ZipSlip."""
    emit_progress("Archive Validation", 15, "Arxiv va maqsadli jild tekshirilmoqda...")
    safe_archive = safe_jail_path(archive_path)
    if not os.path.exists(safe_archive):
        raise FileNotFoundError(f"Arxiv fayli topilmadi: '{archive_path}'")

    if not target_dir:
        base_name = os.path.splitext(os.path.basename(safe_archive))[0]
        target_dir = os.path.join(os.path.dirname(safe_archive), base_name)

    safe_target = safe_jail_path(target_dir, base_dir=os.path.dirname(safe_archive))
    os.makedirs(safe_target, exist_ok=True)

    extracted_count = 0
    total_extracted_bytes = 0

    emit_progress("Extracting", 50, "Fayllar xavfsiz ochilmoqda va yo'llar standartlashtirilmoqda...")

    if zipfile.is_zipfile(safe_archive):
        with zipfile.ZipFile(safe_archive, 'r') as z:
            for member in z.infolist():
                norm_name = member.filename.replace('\\', '/')
                # Prevent ZipSlip
                dest_path = os.path.abspath(os.path.join(safe_target, norm_name))
                if not dest_path.startswith(os.path.abspath(safe_target)):
                    raise PermissionError(f"ZipSlip xavfi aniqlandi: '{member.filename}'")

                if member.is_dir() or norm_name.endswith('/'):
                    os.makedirs(dest_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    with open(dest_path, 'wb') as out_f:
                        out_f.write(z.read(member.filename))
                    extracted_count += 1
                    total_extracted_bytes += member.file_size
    elif tarfile.is_tarfile(safe_archive):
        with tarfile.open(safe_archive, 'r:*') as t:
            for member in t.getmembers():
                norm_name = member.name.replace('\\', '/')
                dest_path = os.path.abspath(os.path.join(safe_target, norm_name))
                if not dest_path.startswith(os.path.abspath(safe_target)):
                    raise PermissionError(f"TarSlip xavfi aniqlandi: '{member.name}'")
                t.extract(member, path=safe_target)
                if member.isfile():
                    extracted_count += 1
                    total_extracted_bytes += member.size
    else:
        raise ValueError("Qo'llab-quvvatlanmaydigan arxiv formati (faqat .zip, .tar, .tar.gz).")

    emit_progress("Complete", 100, f"{extracted_count} ta fayl muvaffaqiyatli ochildi.")
    
    data = {
        "archive_path": safe_archive,
        "target_directory": safe_target,
        "extracted_files_count": extracted_count,
        "total_extracted_bytes": total_extracted_bytes,
        "total_extracted_formatted": f"{round(total_extracted_bytes / 1024, 2)} KB"
    }
    return emit_result(data, success=True)
