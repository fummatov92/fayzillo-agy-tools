import os
from pathlib import Path

# Load .env if present (without hard dependency on python-dotenv)
def _load_dotenv():
    env_file = Path.cwd() / ".env"
    if not env_file.exists():
        # Check tool parent directory or HOME
        env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_load_dotenv()

# ============================================================================
# AGY-TOOL GLOBAL CONFIGURATION
# ============================================================================

HOME_DIR = os.path.expanduser("~")

# 1. Path Jailing & Security
# Comma-separated list of allowed root paths. Default: Desktop, ~/.local, ~/.gemini, ~/Downloads
_raw_allowed = os.getenv("AGY_ALLOWED_DIRS", "")
if _raw_allowed:
    ALLOWED_DIRS = [os.path.realpath(os.path.expanduser(p.strip())) for p in _raw_allowed.split(",") if p.strip()]
else:
    ALLOWED_DIRS = [
        os.path.realpath(os.path.join(HOME_DIR, "Desktop")),
        os.path.realpath(os.path.join(HOME_DIR, ".local")),
        os.path.realpath(os.path.join(HOME_DIR, ".gemini")),
        os.path.realpath(os.path.join(HOME_DIR, "Downloads")),
    ]

# 2. Port Scanner Boundaries (sys module)
PORT_RANGE_START = int(os.getenv("AGY_PORT_RANGE_START", "15800"))
PORT_RANGE_END = int(os.getenv("AGY_PORT_RANGE_END", "15900"))

# 3. Logging & Auditing
LOG_DIR = os.path.realpath(os.path.expanduser(os.getenv("AGY_LOG_DIR", os.path.join(HOME_DIR, ".local/state/agy-tool"))))
MAX_LOG_SIZE_MB = int(os.getenv("AGY_MAX_LOG_SIZE_MB", "5"))

# 4. Media & Multimodal Artifacts
TEMP_MEDIA_DIR = os.path.realpath(os.path.expanduser(os.getenv("AGY_TEMP_MEDIA_DIR", os.path.join(HOME_DIR, "Desktop/temp/media_artifacts"))))
TEMP_SUPER_MEDIA_DIR = os.path.realpath(os.path.expanduser(os.getenv("AGY_TEMP_SUPER_MEDIA_DIR", os.path.join(HOME_DIR, "Desktop/temp/super_media_artifacts"))))

# 5. Biometric Face Recognition
BIOMETRIC_SECRET = os.getenv("AGY_BIOMETRIC_SECRET", "")
BIOMETRIC_DB_PATH = os.path.realpath(os.path.expanduser(os.getenv("AGY_BIOMETRIC_DB_PATH", os.path.join(HOME_DIR, ".gemini/antigravity-cli/faces_db.enc"))))

# 6. Session Management
BRAIN_DIR = os.path.realpath(os.path.expanduser(os.getenv("AGY_BRAIN_DIR", os.path.join(HOME_DIR, ".gemini/antigravity-cli/brain"))))

# 7. Safe Probing Sandbox (doc module)
DEV_DB_SANDBOX_DIR = os.path.realpath(os.path.expanduser(os.getenv("AGY_DEV_DB_SANDBOX_DIR", os.path.join(HOME_DIR, "Desktop/temp/sandbox_db"))))
PROBE_SAFE_TABLES = [t.strip().lower() for t in os.getenv("AGY_PROBE_SAFE_TABLES", "branches,categories,roles,regions,districts,cities,tags,currencies,tariffs,status_types").split(",") if t.strip()]
API_IGNORE_PATTERNS = [p.strip().lower() for p in os.getenv("AGY_API_IGNORE_PATTERNS", "*payme*,*click*,*uzum*,*billing*,*webhook*,*sms*,*auth/login*,*checkout*").split(",") if p.strip()]
