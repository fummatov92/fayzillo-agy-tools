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
    """Ensures paths are strictly within safe directories (e.g. /home/fayzillo)."""
    if base_dir is None:
        base_dir = os.path.expanduser("~")
    
    abs_path = os.path.realpath(os.path.abspath(path))
    abs_base = os.path.realpath(os.path.abspath(base_dir))
    
    if not abs_path.startswith(abs_base):
        raise PermissionError(f"Xavfsizlik cheklovi: '{path}' jildidan tashqariga chiqish taqiqlanadi!")
    return abs_path
