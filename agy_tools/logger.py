import os
import sys
import json
import time
import fcntl
import re
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict
from contextlib import contextmanager

# Known secret patterns
SPECIFIC_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[^-]+-----END [A-Z ]+ PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\b[0-9]{9,10}:[a-zA-Z0-9_-]{35}\b"), "[REDACTED_TELEGRAM_BOT_TOKEN]"),
    (re.compile(r"\bAIzaSy[a-zA-Z0-9_-]{33}\b"), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"\b(?:ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bP@ssw0rd_[a-zA-Z0-9_!@#$%^&*]+"), "[REDACTED_PASSWORD]")
]

QUOTED_KV_PATTERN = re.compile(
    r'''(?i)(["']?(?:password|passwd|pwd|db_pass|db_password|secret|token|api[_-]?key|access_token|private_key|auth_token)["']?\s*[:=]\s*(['"]))((?:(?!\2)(?!\[REDACTED_)[^\r\n])+)(\2)'''
)

UNQUOTED_KV_PATTERN = re.compile(
    r'''(?i)(["']?(?:password|passwd|pwd|db_pass|db_password|secret|token|api[_-]?key|access_token|auth_token)["']?\s*[:=]\s*)(?!['"])(?!\[REDACTED_)([^\s'"#,\}]+)'''
)

SENSITIVE_KEYS = {
    "password", "passwd", "pwd", "db_pass", "db_password", "secret",
    "token", "api_key", "apikey", "api-key", "access_token",
    "private_key", "auth_token", "credentials", "key"
}


def sanitize_string(text: str) -> str:
    """Sanitizes sensitive patterns in strings (tokens, URIs, passwords, flags)."""
    if not isinstance(text, str):
        return text

    # 1. Bearer tokens
    text = re.sub(r'(?i)\b(Bearer\s+)[A-Za-z0-9_\-\.]+', r'\1[REDACTED_TOKEN]', text)

    # 2. Database URIs with credentials
    text = re.sub(
        r'(?i)\b((?:postgres(?:ql)?|redis|mysql|mongodb)://[^:]+:)([^@\s"\']+)(@\S+)',
        r'\1[REDACTED_PASSWORD]\3',
        text
    )
    text = re.sub(
        r'(?i)\b(redis://:)([^@\s"\']+)(@\S+)',
        r'\1[REDACTED_PASSWORD]\3',
        text
    )

    # 3. CLI flags in strings: --password val, -p val, --token val, etc.
    text = re.sub(
        r'(?i)(--(?:password|passwd|token|api[_-]?key|secret)\s+)(\S+)',
        r'\1[REDACTED_SECRET]',
        text
    )
    text = re.sub(
        r'(?i)(--(?:password|passwd|token|api[_-]?key|secret)=)(\S+)',
        r'\1[REDACTED_SECRET]',
        text
    )
    text = re.sub(
        r'(?i)(-p\s+)(\S+)',
        r'\1[REDACTED_PASSWORD]',
        text
    )
    text = re.sub(
        r'(?i)(-p=)(\S+)',
        r'\1[REDACTED_PASSWORD]',
        text
    )

    # 4. Specific known patterns
    for pattern, mask_type in SPECIFIC_PATTERNS:
        text = pattern.sub(mask_type, text)

    # 5. Key-value credentials
    text = QUOTED_KV_PATTERN.sub(r'\g<1>[REDACTED_PASSWORD]\g<4>', text)
    text = UNQUOTED_KV_PATTERN.sub(r'\g<1>[REDACTED_PASSWORD]', text)

    return text


def sanitize_data(data: Any) -> Any:
    """Recursively sanitizes data structures (dicts, lists, primitives)."""
    if data is None:
        return None
    if isinstance(data, str):
        return sanitize_string(data)
    if isinstance(data, (int, float, bool)):
        return data
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            key_str = str(k).lower().replace("-", "_")
            if any(s_key in key_str for s_key in SENSITIVE_KEYS):
                sanitized[k] = "[REDACTED_PASSWORD]"
            else:
                sanitized[k] = sanitize_data(v)
        return sanitized
    if isinstance(data, (list, tuple)):
        sanitized_list = []
        skip_next = False
        for i, item in enumerate(data):
            if skip_next:
                sanitized_list.append("[REDACTED_SECRET]")
                skip_next = False
                continue
            if isinstance(item, str):
                if item in ("--password", "--passwd", "--token", "--api-key", "--secret", "--auth-token"):
                    sanitized_list.append(item)
                    if i + 1 < len(data):
                        skip_next = True
                    continue
                elif item == "-p":
                    sanitized_list.append(item)
                    if i + 1 < len(data):
                        skip_next = True
                    continue
            sanitized_list.append(sanitize_data(item))
        return type(data)(sanitized_list)
    if isinstance(data, set):
        return {sanitize_data(x) for x in data}
    return sanitize_string(str(data))


class RunLogger:
    """Audit logger tracking CLI runs, status, durations, and session context."""

    def __init__(self, log_path: Optional[str] = None):
        if log_path:
            self.log_file = os.path.abspath(os.path.expanduser(log_path))
        else:
            env_path = os.environ.get("AGY_LOG_PATH") or os.environ.get("AGY_LOG_FILE")
            if env_path:
                self.log_file = os.path.abspath(os.path.expanduser(env_path))
            else:
                self.log_file = os.path.expanduser("~/.local/state/agy-tool/runs.jsonl")

        self.log_dir = os.path.dirname(self.log_file)
        self.lock_file = f"{self.log_file}.lock"
        self.rotation_backup = f"{self.log_file}.1"
        self.max_bytes = 5 * 1024 * 1024  # 5 MB

        self.session_id: str = "unknown"
        self.session_path: str = ""
        self.caller_cwd: str = ""
        self.command: str = ""
        self.args: Any = []
        self.start_time: float = time.time()
        self.last_checkpoint: Optional[str] = None
        self.status: str = "SUCCESS"
        self.error_detail: Optional[str] = None
        self.ended: bool = False

    def _ensure_dir_exists(self):
        """Ensure state directory exists with 0o700 permissions."""
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir, mode=0o700, exist_ok=True)
            except Exception:
                pass
        try:
            os.chmod(self.log_dir, 0o700)
        except Exception:
            pass

    @contextmanager
    def _lock(self):
        """Advisory file lock using fcntl.flock to guard concurrent access."""
        self._ensure_dir_exists()
        lock_fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.chmod(self.lock_file, 0o600)
        except Exception:
            pass
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except Exception:
                    pass
        finally:
            try:
                os.close(lock_fd)
            except Exception:
                pass

    def start_run(
        self,
        command: str,
        args: Any = None,
        session_id: Optional[str] = None,
        session_path: Optional[str] = None,
        caller_cwd: Optional[str] = None
    ):
        """Initialize the run context for the executing command."""
        self.start_time = time.time()
        self.command = command or "unknown"
        self.args = sanitize_data(args if args is not None else [])
        self.session_id = session_id or os.environ.get("AGY_CONVERSATION_ID", "unknown")
        self.session_path = session_path or os.environ.get("AGY_SESSION_PATH", "")
        self.caller_cwd = caller_cwd or os.environ.get("AGY_CALLER_CWD", os.getcwd())
        self.last_checkpoint = None
        self.status = "SUCCESS"
        self.error_detail = None
        self.ended = False
        return self

    def checkpoint(self, checkpoint_name: str, pct: Optional[int] = None, detail: Optional[str] = None):
        """Records the latest progress step reached."""
        if pct is not None and detail:
            self.last_checkpoint = f"{checkpoint_name} ({pct}%): {detail}"
        elif pct is not None:
            self.last_checkpoint = f"{checkpoint_name} ({pct}%)"
        else:
            self.last_checkpoint = checkpoint_name

    def set_result(self, success: bool, error: Optional[str] = None):
        """Updates internal status based on emit_result output."""
        if not success:
            self.status = "ERROR"
            if error:
                self.error_detail = sanitize_string(str(error))

    def end_run(self, status: Optional[str] = None, error_detail: Optional[str] = None) -> Optional[dict]:
        """Finalizes the run, computes duration, and writes the JSONL record under advisory lock."""
        if self.ended:
            return None
        self.ended = True

        duration_ms = round((time.time() - self.start_time) * 1000, 2)
        if status:
            self.status = status
        if error_detail:
            self.error_detail = sanitize_string(str(error_detail))

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id or "unknown",
            "session_path": self.session_path or "",
            "caller_cwd": self.caller_cwd or "",
            "command": self.command,
            "args": self.args,
            "status": self.status,
            "duration_ms": duration_ms,
            "error_detail": self.error_detail,
            "last_checkpoint": self.last_checkpoint
        }

        try:
            with self._lock():
                # Check rotation condition
                if os.path.exists(self.log_file):
                    current_size = os.path.getsize(self.log_file)
                    if current_size >= self.max_bytes:
                        if os.path.exists(self.rotation_backup):
                            try:
                                os.remove(self.rotation_backup)
                            except Exception:
                                pass
                        try:
                            os.rename(self.log_file, self.rotation_backup)
                        except Exception:
                            pass

                # Append record
                fd = os.open(self.log_file, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
                try:
                    os.chmod(self.log_file, 0o600)
                except Exception:
                    pass
                with open(fd, "w", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
        except Exception as e:
            # Fall-safe: never crash the caller application due to audit logging failure
            print(f"[AGY RunLogger Warning] Failed to write log: {e}", file=sys.stderr)

        return record

    def get_last_run(self, skip_meta: bool = True) -> Optional[dict]:
        """Reads and returns the last recorded run from JSONL log."""
        if not os.path.exists(self.log_file):
            return None

        records: List[dict] = []
        try:
            with open(self.log_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            continue
        except Exception:
            return None

        if not records:
            return None

        if skip_meta:
            for rec in reversed(records):
                cmd = str(rec.get("command", "")).strip()
                if not (cmd.startswith("sys last-run") or cmd.startswith("sys logs") or cmd in ("last-run", "logs")):
                    return rec
            # Fall back to latest if all are meta
            return records[-1]
        else:
            return records[-1]

    def get_logs(
        self,
        limit: int = 20,
        errors_only: bool = False,
        session_id: Optional[str] = None
    ) -> List[dict]:
        """Returns the most recent log entries matching filters (newest first)."""
        if not os.path.exists(self.log_file):
            return []

        matching: List[dict] = []
        try:
            with open(self.log_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue

                        if errors_only and rec.get("status") == "SUCCESS":
                            continue
                        if session_id and rec.get("session_id") != session_id:
                            continue

                        matching.append(rec)
        except Exception:
            return []

        if not matching:
            return []

        # Return up to `limit` records, most recent first
        return list(reversed(matching[-limit:]))


_default_logger: Optional[RunLogger] = None


def get_logger(log_path: Optional[str] = None) -> RunLogger:
    """Returns a shared singleton RunLogger instance or creates one."""
    global _default_logger
    if _default_logger is None or log_path is not None:
        _default_logger = RunLogger(log_path=log_path)
    return _default_logger
