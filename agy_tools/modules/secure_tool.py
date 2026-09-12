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
            "redact": "Ko'rsatilgan fayl ichidagi sirlarni [REDACTED_...] bilan xavfsiz almashtirish"
        }
    }

PATTERNS = [
    (r"(?:P@ssw0rd_[a-zA-Z0-9_!@#$%^&*]+)", "[REDACTED_PASSWORD]"),
    (r"(?:password|passwd|pwd)\s*[:=]\s*['\"]([^'\"]+)['\"]", "[REDACTED_PASSWORD]"),
    (r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[^-]+-----END [A-Z ]+ PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
    (r"\b[0-9]{9,10}:[a-zA-Z0-9_-]{35}\b", "[REDACTED_TELEGRAM_BOT_TOKEN]"),
    (r"(?:AIzaSy[a-zA-Z0-9_-]{33})", "[REDACTED_GOOGLE_API_KEY]"),
    (r"(?:ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})", "[REDACTED_GITHUB_TOKEN]")
]

def run_secure_scan(args):
    """Scan files for secrets."""
    emit_progress("Scanning Secrets", 20, "Fayllar tekshirilmoqda...")
    target = safe_jail_path(args.path)
    
    findings = []
    if os.path.isfile(target):
        targets = [target]
    else:
        targets = []
        for root, _, files in os.walk(target):
            for f in files:
                if f.endswith((".jsonl", ".log", ".env", ".txt", ".json", ".md")):
                    targets.append(os.path.join(root, f))
                    
    for i, fpath in enumerate(targets):
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for pattern, mask_type in PATTERNS:
                matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
                if matches:
                    findings.append({
                        "file": os.path.relpath(fpath, os.path.expanduser("~")),
                        "type": mask_type,
                        "matches_count": len(matches)
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
    """Redact secrets in target file."""
    emit_progress("Redacting Secrets", 30, "Maxfiy ma'lumotlar tozalanmoqda...")
    target = safe_jail_path(args.path)
    
    if not os.path.isfile(target):
        emit_result(None, success=False, error="Ko'rsatilgan yo'l fayl emas!")
        return
        
    try:
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
            
        redacted_count = 0
        for pattern, mask_type in PATTERNS:
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            if matches:
                redacted_count += len(matches)
                content = re.sub(pattern, mask_type, content, flags=re.DOTALL | re.IGNORECASE)
                
        if not hasattr(args, 'dry_run') or not args.dry_run:
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
                
        emit_progress("Done", 100, "Tozalash yakunlandi.")
        emit_result({
            "file": target,
            "redacted_items": redacted_count,
            "dry_run": getattr(args, 'dry_run', False)
        })
    except Exception as e:
        emit_result(None, success=False, error=str(e))
