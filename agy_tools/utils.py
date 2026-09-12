import json
import sys
import os

def emit_progress(step: str, pct: int, detail: str = ""):
    """Emits live NDJSON progress event to stdout if interactive or requested."""
    payload = {
        "event": "progress",
        "step": step,
        "pct": pct,
        "detail": detail
    }
    # Print as a single compact JSON line
    print(json.dumps(payload), file=sys.stderr, flush=True)

def emit_result(data: dict, success: bool = True, error: str = None):
    """Prints final compact JSON payload for LLM/CLI consumer."""
    out = {
        "success": success,
        "data": data if success else None,
        "error": error if not success else None
    }
    print(json.dumps(out, separators=(',', ':'), ensure_ascii=False))

def safe_jail_path(path: str, base_dir: str = None) -> str:
    """Ensures paths are strictly within safe directories (/home/fayzillo/Desktop and ~/.local/bin)."""
    abs_path = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    
    desktop_dir = os.path.realpath("/home/fayzillo/Desktop")
    local_bin_dir = os.path.realpath(os.path.expanduser("~/.local/bin"))
    
    allowed_dirs = [desktop_dir, local_bin_dir]
    if base_dir:
        allowed_dirs.append(os.path.realpath(os.path.abspath(os.path.expanduser(base_dir))))
        
    is_safe = False
    for allowed in allowed_dirs:
        try:
            if os.path.commonpath([abs_path, allowed]) == allowed:
                is_safe = True
                break
        except (ValueError, Exception):
            continue
            
    if not is_safe:
        raise PermissionError(f"Xavfsizlik cheklovi: '{path}' ruxsat etilgan jildlardan tashqarida!")
    return abs_path

