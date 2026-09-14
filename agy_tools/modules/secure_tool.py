import os
import sys
import re
from agy_tools.utils import emit_progress, emit_result, safe_jail_path

def get_secure_describe():
    return {
        "name": "secure",
        "description": "Loglar, konfiguratsiyalar va fayllardagi maxfiy ma'lumotlarni (parollar, tokenlar, kalitlar) tekshirish va xavfsiz tozalash vositasi.",
        "commands": {
            "scan": "Fayl yoki jilddagi potentsial maxfiy sirlarni qidirish (dry-run)",
            "redact": "Ko'rsatilgan fayl yoki jild ichidagi sirlarni [REDACTED_...] bilan xavfsiz almashtirish"
        }
    }

# Specific secret pattern definitions
SPECIFIC_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[^-]+-----END [A-Z ]+ PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\b[0-9]{9,10}:[a-zA-Z0-9_-]{35}\b"), "[REDACTED_TELEGRAM_BOT_TOKEN]"),
    (re.compile(r"\bAIzaSy[a-zA-Z0-9_-]{33}\b"), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"\b(?:ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bP@ssw0rd_[a-zA-Z0-9_!@#$%^&*]+"), "[REDACTED_PASSWORD]")
]

# Quoted key-value pairs (captures key+delimiter+opening quote in group 1, quote type in group 2, value in group 3, closing quote in group 4)
QUOTED_KV_PATTERN = re.compile(
    r'''(?i)(["']?(?:password|passwd|pwd|db_pass|db_password|secret|token|api[_-]?key|access_token|private_key|auth_token)["']?\s*[:=]\s*(['"]))((?:(?!\2)(?!\[REDACTED_)[^\r\n])+)(\2)'''
)

# Unquoted key-value pairs (captures key+delimiter in group 1, value in group 2)
UNQUOTED_KV_PATTERN = re.compile(
    r'''(?i)(["']?(?:password|passwd|pwd|db_pass|db_password|secret|token|api[_-]?key|access_token|auth_token)["']?\s*[:=]\s*)(?!['"])(?!\[REDACTED_)([^\s'"#,\}]+)'''
)

def redact_text(content: str) -> tuple[str, int]:
    """Redact secrets from text while preserving syntax, keys, and quotes."""
    redacted_count = 0
    
    # 1. Specific token patterns
    for pattern, mask_type in SPECIFIC_PATTERNS:
        matches = pattern.findall(content)
        if matches:
            redacted_count += len(matches)
            content = pattern.sub(mask_type, content)
            
    # 2. Quoted key-value pairs: preserve keys and quotes, redact value
    quoted_matches = QUOTED_KV_PATTERN.findall(content)
    if quoted_matches:
        redacted_count += len(quoted_matches)
        content = QUOTED_KV_PATTERN.sub(r'\g<1>[REDACTED_PASSWORD]\g<4>', content)
        
    # 3. Unquoted key-value pairs: preserve keys, redact value
    unquoted_matches = UNQUOTED_KV_PATTERN.findall(content)
    if unquoted_matches:
        redacted_count += len(unquoted_matches)
        content = UNQUOTED_KV_PATTERN.sub(r'\g<1>[REDACTED_PASSWORD]', content)
        
    return content, redacted_count

IGNORED_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", ".angular", "vendor",
    "__pycache__", ".venv", "venv", "site-packages", ".agents", "target", "out", ".turbo", ".cache"
}

IGNORED_FILE_PREFIXES = (".env",)
ALLOWED_EXTENSIONS = (".jsonl", ".log", ".txt", ".json", ".md", ".yml", ".yaml", ".pbtxt")

def is_ignored_file(filename: str) -> bool:
    """Checks if a file should be ignored during directory security scans/redactions."""
    if filename.startswith(IGNORED_FILE_PREFIXES) or filename.endswith(".env"):
        return True
    return False

def run_secure_scan(args):
    """Scan files for secrets."""
    emit_progress("Scanning Secrets", 20, "Fayllar tekshirilmoqda...")
    target = safe_jail_path(args.path)
    
    if not os.path.exists(target):
        raise FileNotFoundError(f"Ko'rsatilgan yo'l topilmadi: '{target}'")
        
    findings = []
    if os.path.isfile(target):
        targets = [target]
    else:
        targets = []
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for f in files:
                if is_ignored_file(f):
                    continue
                if f.endswith(ALLOWED_EXTENSIONS):
                    targets.append(os.path.join(root, f))
                    
    for i, fpath in enumerate(targets):
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            # Count specific patterns
            for pattern, mask_type in SPECIFIC_PATTERNS:
                matches = pattern.findall(content)
                if matches:
                    findings.append({
                        "file": os.path.relpath(fpath, os.path.expanduser("~")),
                        "type": mask_type,
                        "matches_count": len(matches)
                    })
                    
            # Count quoted KV
            quoted_matches = QUOTED_KV_PATTERN.findall(content)
            if quoted_matches:
                findings.append({
                    "file": os.path.relpath(fpath, os.path.expanduser("~")),
                    "type": "[REDACTED_PASSWORD]",
                    "matches_count": len(quoted_matches)
                })
                
            # Count unquoted KV
            unquoted_matches = UNQUOTED_KV_PATTERN.findall(content)
            if unquoted_matches:
                findings.append({
                    "file": os.path.relpath(fpath, os.path.expanduser("~")),
                    "type": "[REDACTED_PASSWORD]",
                    "matches_count": len(unquoted_matches)
                })
        except Exception:
            pass
            
    emit_progress("Done", 100, "Xavfsizlik tekshiruvi yakunlandi.")
    emit_result({
        "target": target,
        "scanned_files_count": len(targets),
        "leak_detected": len(findings) > 0,
        "findings": findings
    })

def run_secure_redact(args):
    """Redact secrets in target file or directory recursively."""
    emit_progress("Redacting Secrets", 20, "Maxfiy ma'lumotlar tozalanmoqda...")
    target = safe_jail_path(args.path)
    
    if not os.path.exists(target):
        raise FileNotFoundError(f"Fayl yoki jild topilmadi: '{target}'")
        
    dry_run = getattr(args, 'dry_run', False)
    
    if os.path.isfile(target):
        targets = [target]
        is_dir = False
    else:
        is_dir = True
        targets = []
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for f in files:
                if is_ignored_file(f):
                    continue
                if f.endswith(ALLOWED_EXTENSIONS):
                    targets.append(os.path.join(root, f))
                    
    total_redacted = 0
    redacted_files_count = 0
    
    for fpath in targets:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                
            redacted_content, count = redact_text(content)
            if count > 0:
                total_redacted += count
                redacted_files_count += 1
                if not dry_run:
                    target_dir = os.path.dirname(fpath) or "."
                    tmp_file = os.path.join(target_dir, f".tmp_{os.path.basename(fpath)}.{os.getpid()}")
                    try:
                        with open(tmp_file, "w", encoding="utf-8") as f:
                            f.write(redacted_content)
                            f.flush()
                            os.fsync(f.fileno())
                        os.replace(tmp_file, fpath)
                    except Exception:
                        if os.path.exists(tmp_file):
                            try:
                                os.remove(tmp_file)
                            except Exception:
                                pass
                        raise
        except Exception as e:
            if not is_dir:
                raise e
            
    emit_progress("Done", 100, "Tozalash yakunlandi.")
    emit_result({
        "target": target,
        "is_directory": is_dir,
        "scanned_files_count": len(targets),
        "redacted_files_count": redacted_files_count,
        "redacted_items": total_redacted,
        "dry_run": dry_run
    })


