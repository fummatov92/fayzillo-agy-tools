import os
import sys
import re
import shutil
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

def find_tsc_binary(target_path: str) -> str:
    """Find tsc binary in local target node_modules, parent directories, PATH or fallback to npx."""
    # 1. Local target_path/node_modules/.bin/tsc
    local_tsc = os.path.join(target_path, "node_modules", ".bin", "tsc")
    if os.path.isfile(local_tsc) and os.access(local_tsc, os.X_OK):
        return local_tsc

    # 2. Walk up parent directories looking for node_modules/.bin/tsc
    curr = os.path.abspath(target_path)
    while True:
        parent = os.path.dirname(curr)
        if not parent or parent == curr:
            break
        candidate = os.path.join(parent, "node_modules", ".bin", "tsc")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        curr = parent

    # Global or PATH tsc
    which_tsc = shutil.which("tsc")
    if which_tsc:
        return which_tsc

    # 3. Fallback to npx tsc
    return "npx tsc"

def run_debug_check(args):
    """Run local syntax or compiler check without invoking full builds."""
    emit_progress("Checking Syntax", 30, "Loyiha sintaksisi tekshirilmoqda...")
    target_path = safe_jail_path(args.path if hasattr(args, 'path') and args.path else ".")
    
    results = []
    
    # Check for TypeScript project
    tsconfig = os.path.join(target_path, "tsconfig.json")
    if os.path.exists(tsconfig):
        emit_progress("Running TypeCheck", 60, "TypeScript kompilyator tekshiruvi (tsc --noEmit)...")
        tsc_bin = find_tsc_binary(target_path)
        if tsc_bin == "npx tsc":
            cmd_args = ["npx", "tsc", "--noEmit", "--pretty", "false"]
        else:
            cmd_args = [tsc_bin, "--noEmit", "--pretty", "false"]
        res = subprocess.run(cmd_args, shell=False, cwd=target_path, capture_output=True, text=True)
        if res.returncode != 0:
            errors = []
            for line in res.stdout.strip().split("\n"):
                if "error TS" in line:
                    errors.append(line)
            
            if errors:
                results.append({
                    "type": "TypeScript",
                    "status": "Errors Found",
                    "compiler": tsc_bin,
                    "error_count": len(errors),
                    "errors": errors[:15]
                })
            else:
                raw_err = res.stderr.strip() or res.stdout.strip() or "TypeScript compiler command failed to execute."
                err_lines = [line.strip() for line in raw_err.split("\n") if line.strip()]
                results.append({
                    "type": "TypeScript",
                    "status": "Compiler Execution Failed",
                    "compiler": tsc_bin,
                    "error_count": max(1, len(err_lines)),
                    "errors": err_lines[:15]
                })
        else:
            results.append({
                "type": "TypeScript",
                "status": "Clean (No Type Errors)",
                "compiler": tsc_bin
            })
            
    emit_progress("Done", 100, "Tekshiruv yakunlandi.")
    data = {
        "project_path": target_path,
        "checks": results
    }
    emit_result(data)
    return data


def run_bot_test(args):
    """Sandboxed syntax, handler & script verification of Telegram bot."""
    emit_progress("Bot Testing", 10, "Telegram Bot fayllari va sintaksisi tekshirilmoqda...")
    bot_dir = getattr(args, "path", "/home/fayzillo/Desktop/sessiya_connector/bot") or "/home/fayzillo/Desktop/sessiya_connector/bot"
    bot_file = os.path.join(bot_dir, "bot.js")
    
    if not os.path.exists(bot_file):
        emit_result(None, success=False, error=f"Bot fayli topilmadi: {bot_file}")
        return

    checks = []
    
    # Check 1: bot.js syntax
    emit_progress("Bot Testing", 30, "bot.js sintaksisi tekshirilmoqda...")
    res1 = subprocess.run(["node", "-c", bot_file], capture_output=True, text=True)
    if res1.returncode != 0:
        checks.append({
            "target": "bot.js (Node Syntax)",
            "status": "FAIL",
            "error": res1.stderr.strip()
        })
    else:
        checks.append({
            "target": "bot.js (Node Syntax)",
            "status": "PASS",
            "detail": "0 ta sintaksis xatoligi"
        })

    # Check 2: scripts/update_live_msg.js syntax
    upd_script = os.path.join(bot_dir, "scripts", "update_live_msg.js")
    if os.path.exists(upd_script):
        emit_progress("Bot Testing", 60, "update_live_msg.js tekshirilmoqda...")
        res2 = subprocess.run(["node", "-c", upd_script], capture_output=True, text=True)
        if res2.returncode != 0:
            checks.append({
                "target": "scripts/update_live_msg.js",
                "status": "FAIL",
                "error": res2.stderr.strip()
            })
        else:
            checks.append({
                "target": "scripts/update_live_msg.js",
                "status": "PASS",
                "detail": "0 ta sintaksis xatoligi"
            })

    # Check 3: Handlers inspection
    emit_progress("Bot Testing", 80, "Asosiy handlerlar mavjudligi tekshirilmoqda...")
    with open(bot_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    handlers = {
        "Model Failover": "MODEL_FAILOVER_MAP" in content and "isFailoverAttempt" in content,
        "Live Progress Tracker": "startLiveProgress" in content,
        "Handoff / Distill": "handleHandoff" in content,
        "Context Caching": "sessionContextCache" in content and "mtimeMs" in content,
        "PIN WAF Bridge": "approvalState" in content,
    }

    handler_status = {}
    for h_name, present in handlers.items():
        handler_status[h_name] = "ACTIVE" if present else "MISSING"

    all_pass = all(c["status"] == "PASS" for c in checks) and all(v == "ACTIVE" for v in handler_status.values())

    emit_progress("Bot Testing", 100, "Bot tekshiruvi yakunlandi.")
    
    out_format = getattr(args, "format", "table")
    if out_format == "table":
        print("\n=== TELEGRAM BOT SANDBOX TEST HISOBOTI ===")
        print(f"📁 Bot yo'li: {bot_dir}")
        print("\n🔍 Sintaksis Tekshiruvi:")
        for c in checks:
            icon = "✅" if c["status"] == "PASS" else "❌"
            print(f"  {icon} {c['target']:<30}: {c['status']}")
            if c.get("error"):
                print(f"     ⚠️ Xato: {c['error']}")

        print("\n🧩 Integratsiyalangan Tizimlar:")
        for h, s in handler_status.items():
            icon = "✅" if s == "ACTIVE" else "❌"
            print(f"  {icon} {h:<30}: {s}")
        print("-" * 60)
        overall = "BARQAROR VA ISHGA SHAY ✅" if all_pass else "XATOLIKLAR TOPILDI ⚠️"
        print(f"🏁 Yakuniy Xulosa: {overall}\n")

    emit_result({
        "all_pass": all_pass,
        "checks": checks,
        "handlers": handler_status
    })


