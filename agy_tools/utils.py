import json
import sys
import os

_checkpoint_hook = None
_result_hook = None

def set_checkpoint_hook(fn):
    """Sets a global callback hook invoked during emit_progress."""
    global _checkpoint_hook
    _checkpoint_hook = fn

def set_result_hook(fn):
    """Sets a global callback hook invoked during emit_result."""
    global _result_hook
    _result_hook = fn

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
    if _checkpoint_hook is not None:
        try:
            _checkpoint_hook(step, pct, detail)
        except TypeError:
            try:
                _checkpoint_hook(step)
            except Exception:
                pass
        except Exception:
            pass

def emit_result(data: dict, success: bool = True, error: str = None):
    """Prints final compact JSON payload for LLM/CLI consumer."""
    out = {
        "success": success,
        "data": data if success else None,
        "error": error if not success else None
    }
    print(json.dumps(out, separators=(',', ':'), ensure_ascii=False))
    if _result_hook is not None:
        try:
            _result_hook(data, success, error)
        except Exception:
            pass

def safe_jail_path(path: str, base_dir: str = None) -> str:
    """Ensures paths are strictly within safe directories (/home/fayzillo/Desktop and ~/.local)."""
    abs_path = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    
    desktop_dir = os.path.realpath("/home/fayzillo/Desktop")
    local_dir = os.path.realpath(os.path.expanduser("~/.local"))
    
    allowed_dirs = [desktop_dir, local_dir]
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

ALLOWED_PORT_RANGE = (15800, 15900)
FORBIDDEN_SYSTEM_PORTS = {80, 443, 3000, 3306, 4000, 5432, 5433, 6379, 8080, 8090, 9000, 27017}

def validate_safe_port(port: int, allow_range: tuple = ALLOWED_PORT_RANGE) -> bool:
    """Validates that a port is strictly within the allowed JarvisOS range (15800-15900)."""
    if port in FORBIDDEN_SYSTEM_PORTS or not (allow_range[0] <= port <= allow_range[1]):
        raise PermissionError(
            f"Xavfsizlik cheklovi: Port {port} taqiqlangan! "
            f"Sandbox va Dev muhit portlari FAQAT {allow_range[0]}-{allow_range[1]} oralig'ida bo'lishi shart."
        )
    return True

def extract_port_from_url(url: str) -> int:
    """Extracts port integer from a given URL or host:port string, returning None if not found."""
    if not url:
        return None
    import urllib.parse
    parsed = urllib.parse.urlparse(url if "://" in url else f"http://{url}")
    if parsed.port:
        return parsed.port
    return None


