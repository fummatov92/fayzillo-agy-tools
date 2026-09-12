import os
import sys
import re
import subprocess
from agy_tools.utils import emit_progress, emit_result, safe_jail_path

def get_debug_describe():
    return {
        "name": "debug",
        "description": "Xatoliklar loglari (stack trace)ni tahlil qilish, loyiha sintaksisini tekshirish va muammoli kodni aniq ajratib berish vositasi.",
        "commands": {
            "trace": "Xato stack trace matnini tahlil qilib, muammoli fayl, qator va uning atrofidagi kod kontekstini chiqarish",
            "check": "Loyihadagi sintaksis va tiplar xatoliklarini (TypeScript / Python) tezkor tekshirish"
        }
    }

STACK_PATTERNS = [
    # Node/TS/JS: at Object.<anonymous> (/path/to/file.ts:12:34) or at Class.func (path/file.js:10:5)
    r"(?:at\s+(?:[a-zA-Z0-9_$.<>\s]+)\s+\((?:file:\/\/)?([^\s()]+):(\d+):(\d+)\))",
    r"(?:at\s+([^\s()]+):(\d+):(\d+))",
    # Python: File "/path/to/file.py", line 12, in func
    r'File\s+["\']([^"\']+)["\'],\s+line\s+(\d+)(?:,\s+in\s+([a-zA-Z0-9_]+))?'
]

def extract_code_context(filepath: str, target_line: int, context_lines: int = 5) -> dict:
    """Extract code context around the target line number."""
    if not os.path.isfile(filepath):
        return {"error": f"Fayl topilmadi: {filepath}"}
        
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            
        start = max(1, target_line - context_lines)
        end = min(len(lines), target_line + context_lines)
        
        snippet = {}
        for i in range(start, end + 1):
            snippet[str(i)] = lines[i - 1].rstrip()
            
        return {
            "total_lines": len(lines),
            "error_line": target_line,
            "snippet": snippet
        }
    except Exception as e:
        return {"error": str(e)}

def parse_stack_trace(raw_trace: str) -> list:
    """Parse stack trace string into structured items with file and line references."""
    frames = []
    
    for pattern in STACK_PATTERNS:
        matches = re.finditer(pattern, raw_trace)
        for m in matches:
            groups = m.groups()
            filepath = groups[0]
            line_num = int(groups[1])
            
            # Skip node_modules or system libs from primary diagnosis
            is_vendor = "node_modules" in filepath or "/usr/" in filepath or "site-packages" in filepath
            
            frames.append({
                "file": filepath,
                "line": line_num,
                "is_vendor": is_vendor,
                "raw_match": m.group(0)
            })
            
    return frames

def run_debug_trace(args):
    """Analyze a stack trace log and retrieve the targeted code snippet."""
    emit_progress("Parsing Trace", 20, "Stack trace tahlil qilinmoqda...")
    raw_log = args.log if hasattr(args, 'log') and args.log else ""
    
    if not raw_log and not sys.stdin.isatty():
        raw_log = sys.stdin.read()
        
    if not raw_log.strip():
        emit_result(None, success=False, error="Stack trace logi kiritilmadi!")
        return
        
    frames = parse_stack_trace(raw_log)
    
    emit_progress("Locating Culprit", 60, "Muammo yuz bergan asosiy fayl aniqlanmoqda...")
    
    # Priority: first non-vendor frame
    primary_frame = None
    for f in frames:
        if not f["is_vendor"] and os.path.exists(f["file"]):
            primary_frame = f
            break
            
    if not primary_frame and frames:
        # Fallback to the first frame even if path is relative or vendor
        primary_frame = frames[0]
        
    context = None
    if primary_frame and os.path.exists(primary_frame["file"]):
        emit_progress("Extracting Code", 85, "Kod konteksti ajratilmoqda...")
        context = extract_code_context(primary_frame["file"], primary_frame["line"])
        
    emit_progress("Done", 100, "Xatolik tahlili yakunlandi.")
    emit_result({
        "frames_found": len(frames),
        "primary_culprit": primary_frame,
        "code_context": context,
        "all_frames": frames[:5]
    })

def run_debug_check(args):
    """Run local syntax or compiler check without invoking full builds."""
    emit_progress("Checking Syntax", 30, "Loyiha sintaksisi tekshirilmoqda...")
    target_path = safe_jail_path(args.path if hasattr(args, 'path') and args.path else ".")
    
    results = []
    
    # Check for TypeScript project
    tsconfig = os.path.join(target_path, "tsconfig.json")
    if os.path.exists(tsconfig):
        emit_progress("Running TypeCheck", 60, "TypeScript kompilyator tekshiruvi (tsc --noEmit)...")
        # Try local npx tsc or global tsc
        cmd = "npx tsc --noEmit --pretty false"
        res = subprocess.run(cmd, shell=True, cwd=target_path, capture_output=True, text=True)
        if res.returncode != 0:
            errors = []
            for line in res.stdout.strip().split("\n"):
                if "error TS" in line:
                    errors.append(line)
            results.append({
                "type": "TypeScript",
                "status": "Errors Found",
                "error_count": len(errors),
                "errors": errors[:15]
            })
        else:
            results.append({
                "type": "TypeScript",
                "status": "Clean (No Type Errors)"
            })
            
    emit_progress("Done", 100, "Tekshiruv yakunlandi.")
    emit_result({
        "project_path": target_path,
        "checks": results
    })
