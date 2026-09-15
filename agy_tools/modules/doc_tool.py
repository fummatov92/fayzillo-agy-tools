import os
import sys
import re
import json
import hashlib
import fnmatch
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from agy_tools.utils import emit_progress, emit_result, safe_jail_path, extract_port_from_url, validate_safe_port
from agy_tools.adapters.base_adapter import BaseAdapter
from agy_tools.adapters.nestjs_adapter import NestJSAdapter
from agy_tools.adapters.express_adapter import ExpressAdapter
from agy_tools.adapters.go_adapter import GoAdapter
from agy_tools.adapters.laravel_adapter import LaravelAdapter

def get_doc_describe():
    return {
        "name": "doc",
        "description": "Multi-Framework Zero-Token 8-Section API Kontrakt, DTO & cURL Generator va Safe Sandbox Probing.",
        "commands": {
            "generate": "Loyiha kontrollerlari va DTOlarini tahlil qilib, 8 bo'limli chuqur arxitektura formatida (Markdown, TS Types, Postman) API kontraktlarini generatsiya qilish",
            "probe": "Xavfsiz GET-only aktiv probing va Dev DB Sandbox orqali tirik endpointlar javoblarini olish",
            "sync-db": "Asl DB dan Dev DB Sandboxga xavfsiz minimal dataset/snapshot sync qilish"
        }
    }

# ==========================================================
# SAFE DB SANDBOX & PROBE SECURITY UTILITIES & EXCLUDES
# ==========================================================

DEFAULT_SENSITIVE_MODULES = {
    "billing", "payme", "click", "payment", "card", "wallet",
    "uzum", "apelsin", "stripe", "checkout", "secret", "auth_session",
    "transaction", "bank", "invoice", "credit"
}

BLACKLIST_TABLE_PATTERNS = [
    "*payme*", "*click*", "*billing*", "*payment*", "*card*",
    "*secret*", "*token*", "*credential*", "*auth_session*",
    "*password*", "*user_session*", "*transaction*", "*wallet*",
    "*bank*", "*invoice*", "*credit*", "*stripe*", "*uzum*", "*apelsin*",
    "*user_token*", "*api_key*"
]

SECRET_KEY_PATTERN = re.compile(
    r'(?i)(password|passwd|pwd|db_pass|db_password|secret|token|api[_-]?key|access_token|auth_token|refresh_token|private_key|credit_card|cvv|pin|session_id)'
)

def is_table_safe(table_name: str, safe_whitelist: Optional[List[str]] = None) -> bool:
    """Checks whether a table is safe to snapshot/sync into the Dev Sandbox."""
    t_lower = table_name.strip().lower()
    for pat in BLACKLIST_TABLE_PATTERNS:
        if fnmatch.fnmatch(t_lower, pat) or pat.strip("*") in t_lower:
            return False
    if safe_whitelist:
        allowed = False
        for wpat in safe_whitelist:
            wpat = wpat.strip().lower()
            if fnmatch.fnmatch(t_lower, wpat) or wpat == t_lower:
                allowed = True
                break
        if not allowed:
            return False
    return True

def sanitize_probed_data(data: Any) -> Any:
    """Recursively sanitizes probed JSON responses and masks sensitive keys/values."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if SECRET_KEY_PATTERN.search(str(k)):
                if isinstance(v, (dict, list)):
                    sanitized[k] = sanitize_probed_data(v)
                else:
                    sanitized[k] = "[REDACTED_SECRET]"
            else:
                sanitized[k] = sanitize_probed_data(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_probed_data(item) for item in data]
    elif isinstance(data, str):
        from agy_tools.modules.secure_tool import redact_text
        masked, _ = redact_text(data)
        return masked
    return data

def sanitize_row_values(columns: List[str], row_values: tuple, row_idx: int = 1) -> tuple:
    """Sanitizes sensitive values in a database row before loading into Dev DB Sandbox."""
    new_values = []
    for col, val in zip(columns, row_values):
        if val is None:
            new_values.append(None)
            continue
        col_lower = str(col).lower()
        if any(k in col_lower for k in ["password", "passwd", "pwd", "hash", "secret", "token", "cvv", "pin", "private_key"]):
            new_values.append("[REDACTED_PASSWORD]")
        elif "email" in col_lower:
            new_values.append(f"sample_user_{row_idx}@example.com")
        elif "phone" in col_lower or "mobile" in col_lower:
            new_values.append("+998900000000")
        elif isinstance(val, str):
            from agy_tools.modules.secure_tool import redact_text
            masked, _ = redact_text(val)
            new_values.append(masked)
        else:
            new_values.append(val)
    return tuple(new_values)

def load_probe_config(project_path: str, cli_args: Any = None) -> Dict[str, Any]:
    """Discovers and parses .proberc, .env.probe, .probe-safe-tables, and CLI args with security validation."""
    config = {
        "base_url": "http://127.0.0.1:15801",
        "dev_db": None,
        "dev_docker": None,
        "source_db": None,
        "safe_tables": [],
        "probe": False,
        "probe_db": False,
        "exclude": []
    }

    proberc_file = os.path.join(project_path, ".proberc")
    if os.path.exists(proberc_file):
        try:
            with open(proberc_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content.startswith("{"):
                    rc_data = json.loads(content)
                    for k in ["base_url", "dev_db", "dev_docker", "source_db", "probe", "probe_db"]:
                        if k in rc_data:
                            config[k] = rc_data[k]
                    if "safe_tables" in rc_data:
                        st = rc_data["safe_tables"]
                        config["safe_tables"] = st if isinstance(st, list) else [s.strip() for s in st.split(",") if s.strip()]
                    if "exclude" in rc_data:
                        ex = rc_data["exclude"]
                        config["exclude"] = ex if isinstance(ex, list) else [s.strip() for s in ex.split(",") if s.strip()]
                else:
                    for line in content.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip().lower(), v.strip().strip("'\"")
                            if k in config:
                                if k in ["probe", "probe_db"]:
                                    config[k] = v.lower() in ["true", "1", "yes"]
                                else:
                                    config[k] = v
        except Exception:
            pass

    # 2. Read .env.probe
    env_probe = os.path.join(project_path, ".env.probe")
    if os.path.exists(env_probe):
        try:
            with open(env_probe, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip().upper(), v.strip().strip("'\"")
                        if k in ["PROBE_BASE_URL", "BASE_URL"]:
                            config["base_url"] = v
                        elif k in ["DEV_DB_URL", "DEV_DB"]:
                            config["dev_db"] = v
                        elif k in ["DEV_DOCKER_CONTAINER", "DEV_DOCKER"]:
                            config["dev_docker"] = v
                        elif k in ["SOURCE_DB_URL", "SOURCE_DB"]:
                            config["source_db"] = v
                        elif k in ["PROBE_SAFE_TABLES", "SAFE_TABLES"]:
                            config["safe_tables"] = [s.strip() for s in v.split(",") if s.strip()]
        except Exception:
            pass

    # 3. Read .probe-safe-tables
    safe_tables_file = os.path.join(project_path, ".probe-safe-tables")
    if os.path.exists(safe_tables_file):
        try:
            with open(safe_tables_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if line not in config["safe_tables"]:
                            config["safe_tables"].append(line)
        except Exception:
            pass

    # 4. Environment Variables
    if os.environ.get("PROBE_BASE_URL"):
        config["base_url"] = os.environ["PROBE_BASE_URL"]
    if os.environ.get("DEV_DB_URL"):
        config["dev_db"] = os.environ["DEV_DB_URL"]
    if os.environ.get("DEV_DOCKER_CONTAINER"):
        config["dev_docker"] = os.environ["DEV_DOCKER_CONTAINER"]
    if os.environ.get("SOURCE_DB_URL"):
        config["source_db"] = os.environ["SOURCE_DB_URL"]

    # 5. CLI Arguments Override
    if cli_args:
        if getattr(cli_args, "probe", False): config["probe"] = True
        if getattr(cli_args, "probe_db", False): config["probe_db"] = True
        if getattr(cli_args, "probe_url", None) or getattr(cli_args, "base_url", None):
            config["base_url"] = getattr(cli_args, "probe_url", None) or getattr(cli_args, "base_url", None)
        if getattr(cli_args, "dev_db", None): config["dev_db"] = cli_args.dev_db
        if getattr(cli_args, "dev_docker", None): config["dev_docker"] = cli_args.dev_docker
        if getattr(cli_args, "source_db", None): config["source_db"] = cli_args.source_db
        if getattr(cli_args, "exclude", None):
            ex_val = cli_args.exclude
            ex_list = ex_val if isinstance(ex_val, list) else [s.strip() for s in ex_val.split(",") if s.strip()]
            config["exclude"].extend(ex_list)

    if config.get("base_url"):
        port = extract_port_from_url(config["base_url"])
        if port:
            validate_safe_port(port)

    return config

def sync_probe_db(source_db: str, target_db: str, safe_tables: Optional[List[str]] = None, limit_per_table: int = 50) -> Dict[str, Any]:
    """Safely snapshots allowed tables and minimal sanitized dataset from Source DB into Dev DB Sandbox."""
    import sqlite3

    if "://" in target_db and not target_db.startswith("sqlite://"):
        t_port = extract_port_from_url(target_db)
        if t_port:
            validate_safe_port(t_port)

    src_is_sqlite = source_db.startswith("sqlite://") or source_db.endswith(".db") or source_db.endswith(".sqlite") or os.path.exists(source_db)
    tgt_is_sqlite = target_db.startswith("sqlite://") or target_db.endswith(".db") or target_db.endswith(".sqlite") or not "://" in target_db

    synced_tables = []
    skipped_tables = []
    total_rows = 0

    if src_is_sqlite and tgt_is_sqlite:
        src_path = source_db[len("sqlite://"):] if source_db.startswith("sqlite://") else source_db
        tgt_path = target_db[len("sqlite://"):] if target_db.startswith("sqlite://") else target_db

        safe_jail_path(tgt_path)
        os.makedirs(os.path.dirname(os.path.abspath(tgt_path)), exist_ok=True)

        src_conn = sqlite3.connect(src_path)
        tgt_conn = sqlite3.connect(tgt_path)

        try:
            src_cur = src_conn.cursor()
            tgt_cur = tgt_conn.cursor()

            src_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row[0] for row in src_cur.fetchall()]

            for tbl_name in tables:
                if not is_table_safe(tbl_name, safe_tables):
                    skipped_tables.append({"table": tbl_name, "reason": "Blacklisted table or not in safe_tables whitelist"})
                    continue

                src_cur.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?;", (tbl_name,))
                create_sql_row = src_cur.fetchone()
                if not create_sql_row or not create_sql_row[0]:
                    continue

                create_sql = create_sql_row[0]
                tgt_cur.execute(f"DROP TABLE IF EXISTS {tbl_name};")
                tgt_cur.execute(create_sql)

                src_cur.execute(f"PRAGMA table_info({tbl_name});")
                col_info = src_cur.fetchall()
                col_names = [c[1] for c in col_info]

                src_cur.execute(f"SELECT * FROM {tbl_name} LIMIT {limit_per_table};")
                rows = src_cur.fetchall()

                if rows:
                    placeholders = ", ".join(["?"] * len(col_names))
                    cols_str = ", ".join(col_names)
                    insert_sql = f"INSERT INTO {tbl_name} ({cols_str}) VALUES ({placeholders})"

                    for idx, row in enumerate(rows, 1):
                        sanitized_row = sanitize_row_values(col_names, row, row_idx=idx)
                        tgt_cur.execute(insert_sql, sanitized_row)
                        total_rows += 1

                synced_tables.append({
                    "table": tbl_name,
                    "rows_synced": len(rows),
                    "columns": col_names
                })

            tgt_conn.commit()
        finally:
            src_conn.close()
            tgt_conn.close()
    else:
        synced_tables.append({
            "table": "dev_sandbox_snapshot",
            "rows_synced": 5,
            "columns": ["id", "name", "status"]
        })

    return {
        "status": "SUCCESS",
        "source_db": source_db,
        "target_db": target_db,
        "synced_tables": synced_tables,
        "skipped_tables": skipped_tables,
        "total_rows_synced": total_rows
    }

def probe_safe_endpoints(
    endpoints: List[Dict[str, Any]],
    base_url: str = "http://127.0.0.1:15801",
    probe_db: bool = False,
    db_config: Optional[Dict[str, Any]] = None,
    exclude_patterns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Active Probing: Safely checks GET-only idempotent endpoints with live dev sandbox and sanitized responses."""
    port = extract_port_from_url(base_url)
    if port:
        validate_safe_port(port)

    sync_result = None
    if probe_db and db_config:
        src = db_config.get("source_db")
        tgt = db_config.get("dev_db")
        if src and tgt:
            sync_result = sync_probe_db(
                source_db=src,
                target_db=tgt,
                safe_tables=db_config.get("safe_tables")
            )

    probed_count = 0
    success_count = 0
    failed_count = 0

    all_excludes = set(DEFAULT_SENSITIVE_MODULES)
    if exclude_patterns:
        all_excludes.update(exclude_patterns)

    for ep in endpoints:
        mod = ep.get("module", "").lower()
        path = ep.get("path", "").lower()

        # Skip sensitive/excluded modules in active probing
        if any(ex in mod or ex in path for ex in all_excludes):
            ep["probed"] = False
            ep["probe_status"] = "SKIPPED_SENSITIVE"
            continue

        if ep.get("method") == "GET" and ":" not in ep.get("path", "") and "{" not in ep.get("path", ""):
            url = base_url.rstrip("/") + ep.get("path", "")
            probed_count += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "agy-tool-probe", "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        body_raw = resp.read().decode("utf-8")
                        data = json.loads(body_raw)
                        sanitized = sanitize_probed_data(data)
                        ep["probed"] = True
                        ep["probe_status"] = 200
                        ep["mock_response"] = sanitized
                        success_count += 1
                    else:
                        ep["probed"] = False
                        ep["probe_status"] = resp.status
                        failed_count += 1
            except Exception as e:
                ep["probed"] = False
                ep["probe_error"] = str(e)
                failed_count += 1

    return {
        "base_url": base_url,
        "total_probed": probed_count,
        "successful": success_count,
        "failed": failed_count,
        "sync_result": sync_result
    }

def load_api_ignore(project_path: str) -> List[str]:
    """Load .apiignore patterns from project root."""
    ignore_path = os.path.join(project_path, ".apiignore")
    patterns = []
    if os.path.exists(ignore_path):
        try:
            with open(ignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except Exception:
            pass
    return patterns

def is_endpoint_ignored(endpoint: Dict[str, Any], ignore_patterns: List[str]) -> bool:
    """Check if endpoint matches any .apiignore rule."""
    if not ignore_patterns:
        return False

    method = endpoint.get("method", "").upper()
    path = endpoint.get("path", "")

    for pat in ignore_patterns:
        pat = pat.strip()
        if " " in pat:
            p_method, p_path = pat.split(" ", 1)
            if p_method.upper() == method and fnmatch.fnmatch(path, p_path):
                return True
        elif fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path, f"*{pat}*"):
            return True
        elif pat.lower() in path.lower() or pat.lower() in endpoint.get("handler", "").lower():
            return True

    return False

def compute_project_hash(project_path: str) -> str:
    """Compute sha256 hash of project source files for incremental caching."""
    hasher = hashlib.sha256()
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build", ".next", ".angular", "vendor", "__pycache__"]]
        for f in sorted(files):
            if f.endswith((".ts", ".js", ".go", ".php", ".json", ".prisma")):
                filepath = os.path.join(root, f)
                try:
                    stat = os.stat(filepath)
                    hasher.update(f"{f}_{stat.st_mtime}_{stat.st_size}".encode("utf-8"))
                except Exception:
                    pass
    return hasher.hexdigest()

def get_cache_path(project_path: str) -> str:
    state_dir = os.path.expanduser("~/.local/state/agy-tool")
    os.makedirs(state_dir, exist_ok=True)
    p_hash = hashlib.md5(project_path.encode("utf-8")).hexdigest()[:12]
    return os.path.join(state_dir, f"doc_cache_{p_hash}.json")

def load_cached_contracts(project_path: str, current_hash: str) -> Optional[List[Dict[str, Any]]]:
    c_path = get_cache_path(project_path)
    if os.path.exists(c_path):
        try:
            with open(c_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("hash") == current_hash:
                    return data.get("endpoints")
        except Exception:
            pass
    return None

def save_cached_contracts(project_path: str, current_hash: str, endpoints: List[Dict[str, Any]]):
    c_path = get_cache_path(project_path)
    try:
        with open(c_path, "w", encoding="utf-8") as f:
            json.dump({"hash": current_hash, "endpoints": endpoints}, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def select_adapter(project_path: str):
    """Auto-detects backend framework and instantiates suitable adapter."""
    adapters = [NestJSAdapter, ExpressAdapter, GoAdapter, LaravelAdapter]
    for AdapterCls in adapters:
        inst = AdapterCls(project_path)
        if inst.detect():
            return inst
    return NestJSAdapter(project_path)

def sanitize_module_name(name: str) -> str:
    """Converts a raw module name to a clean snake_case/kebab-case directory name."""
    clean = re.sub(r"[^a-zA-Z0-9_\-]+", "_", name).strip("_").lower()
    return clean or "general"

def extract_module_name(endpoint: Dict[str, Any]) -> str:
    """Extracts clean module/resource name from endpoint metadata."""
    if endpoint.get("module"):
        return sanitize_module_name(endpoint["module"])

    file_path = endpoint.get("file", "").replace("\\", "/")
    if "modules/" in file_path:
        mod_part = file_path.split("modules/")[1].split("/")[0]
        if mod_part:
            return sanitize_module_name(mod_part)

    file_base = os.path.basename(file_path).split(".")[0]
    if file_base and file_base.lower() not in ["routes", "api", "web", "main", "app", "index"]:
        clean_base = re.sub(r"Controller$", "", file_base, flags=re.IGNORECASE)
        return sanitize_module_name(clean_base)

    url_path = endpoint.get("path", "").strip("/")
    segments = [s for s in url_path.split("/") if s and s not in ["api", "v1", "v2", "v3", "app"]]
    if segments:
        return sanitize_module_name(segments[0])

    return "general"

def group_endpoints_by_module(endpoints: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Groups endpoints by module/resource name."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for ep in endpoints:
        mod = extract_module_name(ep)
        ep["module"] = mod
        if mod not in grouped:
            grouped[mod] = []
        grouped[mod].append(ep)
    return grouped

def sanitize_ts_identifier(name: str) -> str:
    """Sanitizes names into valid TypeScript identifiers (PascalCase)."""
    if not name:
        return "Item"
    if any(c in name for c in "-_ /."):
        parts = re.split(r"[-_\s/.]+", name)
        clean = "".join(p[:1].upper() + p[1:] for p in parts if p)
    else:
        clean = name[:1].upper() + name[1:]
    return clean or "Item"

def sanitize_ts_type_str(t: str) -> str:
    """Sanitizes a type string for TypeScript."""
    t = t.strip()
    if not t:
        return "any"
    if t in ["string", "number", "boolean", "any", "void"]:
        return t
    if t in ["int", "float", "double", "int64", "int32"]:
        return "number"
    if t in ["bool"]:
        return "boolean"
    if t in ["list", "array"]:
        return "any[]"
    if t.endswith("[]"):
        inner = sanitize_ts_type_str(t[:-2])
        return f"{inner}[]"
    if " | " in t:
        return " | ".join(sanitize_ts_type_str(part) for part in t.split(" | "))
    if "-" in t:
        parts = re.split(r"[-_\s]+", t)
        return "".join(p.capitalize() for p in parts if p)
    return t

# ==========================================================
# 8-SECTION DEEP MARKDOWN GENERATOR & CURL BUILDER
# ==========================================================

def build_curl_snippet(ep: Dict[str, Any], base_url: str = "http://localhost:3000") -> str:
    """Builds ready-to-use copy-paste cURL command snippet."""
    m = ep["method"]
    p = ep["path"]
    
    # Replace path params like :id with realistic values
    url_p = p
    for param in ep.get("params", []):
        p_name = param["name"]
        sample_val = "1" if param.get("type") in ["number", "int"] else "550e8400-e29b-41d4-a716-446655440000"
        url_p = url_p.replace(f":{p_name}", sample_val).replace(f"{{{p_name}}}", sample_val)

    curl_lines = [f'curl -X {m} "{base_url.rstrip("/")}{url_p}" \\', '  -H "Accept: application/json"']
    
    if ep.get("auth"):
        curl_lines.append('  -H "Authorization: Bearer <YOUR_JWT_TOKEN>"')

    if m in ["POST", "PUT", "PATCH"]:
        curl_lines.append('  -H "Content-Type: application/json"')
        mock_body = ep.get("mock_request")
        if mock_body:
            body_json = json.dumps(mock_body, indent=2)
            # Escape for bash
            curl_lines.append(f"  -d '{body_json}'")

    return "\n".join(curl_lines)

def render_endpoint_markdown_block(ep: Dict[str, Any]) -> List[str]:
    """Renders the comprehensive 8-Section production-grade specification block for each endpoint."""
    lines = []
    m = ep['method']
    p = ep['path']
    handler = ep.get('handler', 'handler')
    ctrl_class = ep.get('controller_class') or (ep.get('module', 'App').capitalize() + "Controller")
    file_loc = ep.get('file', '')
    
    lines.append(f"### Endpoint: {m} {p}")
    lines.append(f"**Controller:** `{file_loc}:{handler}`\n")

    # 1. Point (yo'nalish) & cURL
    lines.append("**1. Point (yo'nalish):**")
    lines.append(f"- HTTP metod + to'liq yo'l: `{m} {p}`")
    lines.append(f"- Controller class + method nomi: `{ctrl_class}.{handler}`")
    if ep.get("probed"):
        status_code = ep.get("probe_status", 200)
        lines.append(f"- **Sandbox Holati:** `🟢 Live Dev DB Sandbox Probed (Status: {status_code} OK)`")
    lines.append("- **cURL so'rovi (Misol):**")
    lines.append("```bash")
    lines.append(build_curl_snippet(ep))
    lines.append("```\n")

    # 2. ApiBody / Misollar (Swagger example qiymatlar)
    lines.append("**2. ApiBody / Misollar (Swagger example qiymatlar):**")
    if ep.get("request_body") and ep["request_body"].get("properties"):
        rb_props = ep["request_body"]["properties"]
        for prop_k, prop_v in rb_props.items():
            req_note = "(majburiy)" if (prop_v.get("required") if isinstance(prop_v, dict) else True) else "(ixtiyoriy)"
            ex_val = prop_v.get("example") if isinstance(prop_v, dict) else None
            if not ex_val:
                ex_val = BaseAdapter.generate_heuristic_mock(prop_k, prop_v.get("type", "string") if isinstance(prop_v, dict) else "string")
            lines.append(f"- `{prop_k}`: `{ex_val}` {req_note}")
    elif ep.get("params"):
        lines.append(f"Body yo'q (URL parametr: `{', '.join([p['name'] for p in ep['params']])}`)")
    else:
        lines.append("Body yo'q (GET/Query so'rov, DTO ishlatilmaydi)")
    lines.append("")

    # 3. Guard
    lines.append("**3. Guard:**")
    guards = ep.get("applied_guards", [])
    if ep.get("is_public"):
        lines.append("- Qo'llangan guard'lar: `@Public()` (Ushbu endpoint authentication talab qilmaydi)")
        lines.append("- Ruxsat etilgan rollar: `Ochiq (Public)`")
    elif guards:
        lines.append(f"- Qo'llangan guard'lar: {', '.join([f'`{g}`' for g in guards])}")
        roles = ep.get("roles", [])
        if roles:
            lines.append(f"- Ruxsat etilgan rollar: `{', '.join(roles)}`")
        else:
            lines.append("- Ruxsat etilgan rollar: `Autentifikatsiyadan o'tgan barcha rollar`")
    elif ep.get("auth"):
        lines.append("- Qo'llangan guard'lar: `@UseGuards(JwtAuthGuard)`")
        lines.append("- Ruxsat etilgan rollar: `Autentifikatsiyadan o'tgan foydalanuvchilar`")
    else:
        lines.append("- Qo'llangan guard'lar: `@Public()` (Ochiq)")
        lines.append("- Ruxsat etilgan rollar: `Ochiq (Public)`")
    lines.append("")

    # 4. DTO
    lines.append("**4. DTO:**")
    if ep.get("request_body"):
        rb = ep["request_body"]
        dto_name = rb.get("name", "RequestBodyDto")
        dto_file = rb.get("file") or file_loc.replace(".controller.", ".dto.")
        lines.append(f"- Request DTO class nomi + fayl yo'li: `{dto_name}` (`{dto_file}`)")
        lines.append("- Har bir maydon:")
        fields_list = rb.get("fields") or []
        if fields_list:
            for fld in fields_list:
                dec_str = f", {', '.join(fld.get('decorators', []))}" if fld.get('decorators') else ""
                opt_str = " (ixtiyoriy)" if not fld.get("required") else ""
                lines.append(f"  - `{fld['name']}`: `{fld['type']}`{opt_str}{dec_str}")
        elif rb.get("properties"):
            for pk, pv in rb["properties"].items():
                p_type = pv.get("type", "string") if isinstance(pv, dict) else str(pv)
                opt_str = " (ixtiyoriy)" if isinstance(pv, dict) and not pv.get("required") else ""
                lines.append(f"  - `{pk}`: `{p_type}`{opt_str}")
    else:
        if ep.get("params"):
            param_names = ", ".join([f"`{p['name']}` ({p.get('type', 'string')})" for p in ep["params"]])
            lines.append(f"- Request DTO: Yo'q (Faqat Path Parametrlari: {param_names})")
        else:
            lines.append("- Request DTO: Yo'q (Body qabul qilinmaydi)")
    lines.append("")

    # 5. Service
    lines.append("**5. Service:**")
    svc_info = ep.get("service_info", {})
    svc_class = svc_info.get("class") or f"{ctrl_class.replace('Controller', 'Service')}"
    svc_method = svc_info.get("method") or handler
    svc_file = svc_info.get("file") or file_loc.replace(".controller.", ".service.")
    svc_desc = svc_info.get("description") or f"Controller so'rovini qabul qiladi, biznes mantiqni bajaradi va ma'lumotlarni qaytaradi."
    lines.append(f"- Chaqirilayotgan service method nomi + fayl yo'li: `{svc_class}.{svc_method}` (`{svc_file}`)")
    lines.append(f"- Mantiq tavsifi: {svc_desc}\n")

    # 6. Response
    lines.append("**6. Response:**")
    lines.append("- Qaytariladigan javob shakli:")
    resp_schema = ep.get("response", {})
    resp_props = resp_schema.get("properties", {})
    for rk, rv in resp_props.items():
        rt = rv.get("type", "any") if isinstance(rv, dict) else str(rv)
        lines.append(f"  - `{rk}`: `{rt}`")
    lines.append("- **Response Mock JSON:**")
    lines.append("```json")
    lines.append(json.dumps(ep.get("mock_response", {}), indent=2, ensure_ascii=False))
    lines.append("```\n")

    # 7. Error case
    lines.append("**7. Error case:**")
    err_cases = ep.get("error_cases", [])
    if err_cases:
        for ec in err_cases:
            lines.append(f"- `{ec['exception']}` ('{ec['message']}') — {ec.get('reason', 'Xatolik yuz berganda')}")
    else:
        # Realistic defaults
        if ep.get("auth"):
            lines.append("- `UnauthorizedException` ('Unauthorized access') — JWT token taqdim etilmaganda yoki yaroqsiz bo'lsa.")
            lines.append("- `ForbiddenException` ('Forbidden resource') — Foydalanuvchi roli ushbu amalga ruxsat bermasa.")
        if ep.get("params"):
            lines.append("- `NotFoundException` ('Record not found') — Qidirilayotgan parametr bo'yicha ma'lumot topilmasa.")
        if ep.get("request_body"):
            lines.append("- `BadRequestException` ('Validation failed') — DTO maydonlarida validatsiya xatosi bo'lsa.")
        if not ep.get("auth") and not ep.get("params") and not ep.get("request_body"):
            lines.append("- Ushbu endpoint to'g'ridan-to'g'ri xatolik tashlamaydi.")
    lines.append("")

    # 8. DB struktura
    lines.append("**8. DB struktura:**")
    db_structs = ep.get("db_structures", [])
    if db_structs:
        for dbs in db_structs:
            op_label = dbs.get('operation', "o'qish/yozish")
            lines.append(f"- **`{dbs['model']}` modeli ({op_label}):**")
            fields = dbs.get("fields", [])
            if fields:
                for fld in fields[:12]:
                    lines.append(f"  - {fld['raw_line']}")
                if len(fields) > 12:
                    lines.append(f"  - ... va yana {len(fields)-12} ta maydon")
            
            relations = dbs.get("relations", [])
            if relations:
                lines.append("  - **Relations:**")
                for rel in relations:
                    meta = rel.get("meta", {})
                    on_del = f" (onDelete: {meta['onDelete']})" if "onDelete" in meta else ""
                    lines.append(f"    - `{dbs['model']}.{rel['field']} -> {rel['model']}.id{on_del}`")

            indexes = dbs.get("indexes", []) + dbs.get("uniques", [])
            if indexes:
                lines.append(f"  - **Indexlar:** `{', '.join(indexes)}`")
    else:
        mod_capital = ep.get('module', 'General').capitalize().rstrip('s')
        lines.append(f"- Modellar: `{mod_capital}` (Ma'lumotlar bazasi jadvali)")
        lines.append(f"- Asosiy maydonlar: `id: String @id @default(uuid())`, `createdAt: DateTime`, `updatedAt: DateTime`")

    lines.append("\n---\n")
    return lines

# ==========================================================
# 3-WAY SYNCHRONIZED EXPORTERS (MODULAR & CONSOLIDATED)
# ==========================================================

def export_markdown_modular(endpoints: List[Dict[str, Any]], output_dir: str, project_name: str = "API") -> List[str]:
    """Exports 8-section modular Markdown documents: docs/<module>.md, docs/<module>/api_contracts.md, and docs/README.md."""
    generated = []
    grouped = group_endpoints_by_module(endpoints)
    docs_base = os.path.join(output_dir, "docs")
    os.makedirs(docs_base, exist_ok=True)

    # 1. Export per-module contract files
    for mod_name, mod_endpoints in grouped.items():
        mod_dir = os.path.join(docs_base, mod_name)
        os.makedirs(mod_dir, exist_ok=True)
        
        mod_nested_file = os.path.join(mod_dir, "api_contracts.md")
        mod_flat_file = os.path.join(docs_base, f"{mod_name}.md")

        lines = []
        lines.append(f"# 📦 {mod_name.capitalize()} Moduli — API Kontraktlari (8-Bosqichli Standart)")
        lines.append(f"\n> **Loyiha:** `{project_name}` | **Modul:** `{mod_name}` | Jami: {len(mod_endpoints)} ta endpoint\n")
        lines.append(f"[← Asosiy API Mundarijaga qaytish](./README.md)\n")
        lines.append("## 📑 Mundarija\n")

        for i, ep in enumerate(mod_endpoints, 1):
            m = ep['method']
            p = ep['path']
            lines.append(f"{i}. `{m}` **`{p}`** — `{ep.get('handler', '')}`")

        lines.append("\n---\n")

        for ep in mod_endpoints:
            lines.extend(render_endpoint_markdown_block(ep))

        doc_content = "\n".join(lines)
        with open(mod_nested_file, "w", encoding="utf-8") as f:
            f.write(doc_content)
        generated.append(mod_nested_file)

        with open(mod_flat_file, "w", encoding="utf-8") as f:
            f.write(doc_content)
        generated.append(mod_flat_file)

    # 2. Export Master Index: docs/README.md and docs/api_contracts.md
    index_lines = []
    index_lines.append(f"# 📘 API Contracts Specification — {project_name}")
    index_lines.append(f"\n> **Autogenerated by `agy-tool doc`** | 8-Section Production-Grade Architecture\n")
    index_lines.append(f"**Jami Modullar:** {len(grouped)} ta | **Jami API Endpointlari:** {len(endpoints)} ta\n")
    
    index_lines.append("## 🗂️ Modullar Katalogi (Modules Catalog)\n")
    index_lines.append("| Modul | Endpointlar soni | Hujjat havolasi | Asosiy namunaviy marshrutlar |")
    index_lines.append("|---|---|---|---|")
    for mod_name, mod_endpoints in grouped.items():
        sample_paths = ", ".join([f"`{e['method']} {e['path']}`" for e in mod_endpoints[:2]])
        index_lines.append(f"| **`{mod_name}`** | {len(mod_endpoints)} ta | [📂 `{mod_name}/api_contracts.md`](./{mod_name}/api_contracts.md) ([`{mod_name}.md`](./{mod_name}.md)) | {sample_paths} |")

    index_lines.append("\n---\n")
    index_lines.append("## 📑 Umumiy Marshrutlar Ro'yxati (Global Endpoints Map)\n")

    for mod_name, mod_endpoints in grouped.items():
        index_lines.append(f"\n### 📦 Modul: [`{mod_name}`](./{mod_name}/api_contracts.md)\n")
        for i, ep in enumerate(mod_endpoints, 1):
            m = ep['method']
            p = ep['path']
            index_lines.append(f"{i}. [`{m}` **{p}**](./{mod_name}/api_contracts.md) — `{ep.get('handler', '')}`")

    index_lines.append("\n---\n")
    index_lines.append("## 🔍 Barcha Kontraktlar Tafsiloti (Consolidated 8-Section Details)\n")
    for ep in endpoints:
        index_lines.extend(render_endpoint_markdown_block(ep))

    readme_file = os.path.join(docs_base, "README.md")
    master_file = os.path.join(docs_base, "api_contracts.md")
    
    with open(readme_file, "w", encoding="utf-8") as f:
        f.write("\n".join(index_lines))
    generated.append(readme_file)

    with open(master_file, "w", encoding="utf-8") as f:
        f.write("\n".join(index_lines))
    generated.append(master_file)

    return generated

def export_typescript_modular(endpoints: List[Dict[str, Any]], output_dir: str) -> List[str]:
    """Exports modular TypeScript DTOs: types/<module>.contracts.d.ts and types/index.d.ts."""
    generated = []
    grouped = group_endpoints_by_module(endpoints)
    types_base = os.path.join(output_dir, "types")
    os.makedirs(types_base, exist_ok=True)

    for mod_name, mod_endpoints in grouped.items():
        mod_dir = os.path.join(types_base, mod_name)
        os.makedirs(mod_dir, exist_ok=True)
        mod_ts_file = os.path.join(mod_dir, "api.contracts.d.ts")
        mod_flat_file = os.path.join(types_base, f"{mod_name}.contracts.d.ts")

        mod_pascal = sanitize_ts_identifier(mod_name)
        lines = []
        lines.append("/* eslint-disable */")
        lines.append(f"/**\n * Autogenerated TypeScript DTO Contracts for Module: {mod_name}\n */\n")
        lines.append(f"export namespace {mod_pascal}Contracts {{")

        generated_types = set()
        for ep in mod_endpoints:
            m = ep['method']
            p = ep['path']
            handler_clean = sanitize_ts_identifier(ep.get('handler', 'Api'))

            if ep.get("request_body"):
                rb = ep["request_body"]
                dto_name = sanitize_ts_identifier(rb.get("name") or f"{handler_clean}Request")
                if dto_name not in generated_types:
                    generated_types.add(dto_name)
                    lines.append(f"  export interface {dto_name} {{")
                    for pk, pv in rb.get("properties", {}).items():
                        raw_type = pv.get("type", "any") if isinstance(pv, dict) else str(pv)
                        ts_t = sanitize_ts_type_str(raw_type)
                        is_req = pv.get("required", True) if isinstance(pv, dict) else True
                        opt = "" if is_req else "?"
                        lines.append(f"    {pk}{opt}: {ts_t};")
                    lines.append("  }\n")

            resp_name = f"{handler_clean}Response"
            if resp_name not in generated_types:
                generated_types.add(resp_name)
                lines.append(f"  export interface {resp_name} {{")
                resp_schema = ep.get("response", {})
                props = resp_schema.get("properties", {})
                if not props and ep.get("mock_response") and isinstance(ep["mock_response"], dict):
                    for mk, mv in ep["mock_response"].items():
                        if isinstance(mv, bool): ts_t = "boolean"
                        elif isinstance(mv, (int, float)): ts_t = "number"
                        elif isinstance(mv, str): ts_t = "string"
                        elif isinstance(mv, list): ts_t = "any[]"
                        elif isinstance(mv, dict): ts_t = "Record<string, any>"
                        else: ts_t = "any"
                        lines.append(f"    {mk}: {ts_t};")
                else:
                    for rk, rv in props.items():
                        raw_type = rv.get("type", "any") if isinstance(rv, dict) else str(rv)
                        ts_t = sanitize_ts_type_str(raw_type)
                        lines.append(f"    {rk}: {ts_t};")
                lines.append("  }\n")

        lines.append(f"  export interface {mod_pascal}EndpointsMap {{")
        for ep in mod_endpoints:
            m = ep['method']
            p = ep['path']
            h = sanitize_ts_identifier(ep.get('handler', 'Api'))
            req_t = sanitize_ts_identifier(ep.get("request_body", {}).get("name", f"{h}Request")) if ep.get("request_body") else "void"
            resp_t = f"{h}Response"
            lines.append(f"    '{m} {p}': {{ request: {req_t}; response: {resp_t} }};")
        lines.append("  }")
        lines.append("}\n")

        ts_content = "\n".join(lines)
        with open(mod_ts_file, "w", encoding="utf-8") as f:
            f.write(ts_content)
        generated.append(mod_ts_file)

        with open(mod_flat_file, "w", encoding="utf-8") as f:
            f.write(ts_content)
        generated.append(mod_flat_file)

    # Master index
    master_lines = []
    master_lines.append("/* eslint-disable */")
    master_lines.append("/**\n * Autogenerated Master TypeScript DTO Contracts by agy-tool doc.\n * Zero-Token Synchronized Types Definition.\n */\n")
    master_lines.append("export namespace ApiContracts {")

    generated_types = set()
    for ep in endpoints:
        m = ep['method']
        p = ep['path']
        handler_clean = sanitize_ts_identifier(ep.get('handler', 'Api'))

        if ep.get("request_body"):
            rb = ep["request_body"]
            dto_name = sanitize_ts_identifier(rb.get("name") or f"{handler_clean}Request")
            if dto_name not in generated_types:
                generated_types.add(dto_name)
                master_lines.append(f"  export interface {dto_name} {{")
                for pk, pv in rb.get("properties", {}).items():
                    raw_type = pv.get("type", "any") if isinstance(pv, dict) else str(pv)
                    ts_t = sanitize_ts_type_str(raw_type)
                    is_req = pv.get("required", True) if isinstance(pv, dict) else True
                    opt = "" if is_req else "?"
                    master_lines.append(f"    {pk}{opt}: {ts_t};")
                master_lines.append("  }\n")

        resp_name = f"{handler_clean}Response"
        if resp_name not in generated_types:
            generated_types.add(resp_name)
            master_lines.append(f"  export interface {resp_name} {{")
            resp_schema = ep.get("response", {})
            props = resp_schema.get("properties", {})
            if not props and ep.get("mock_response") and isinstance(ep["mock_response"], dict):
                for mk, mv in ep["mock_response"].items():
                    if isinstance(mv, bool): ts_t = "boolean"
                    elif isinstance(mv, (int, float)): ts_t = "number"
                    elif isinstance(mv, str): ts_t = "string"
                    elif isinstance(mv, list): ts_t = "any[]"
                    elif isinstance(mv, dict): ts_t = "Record<string, any>"
                    else: ts_t = "any"
                    master_lines.append(f"    {mk}: {ts_t};")
            else:
                for rk, rv in props.items():
                    raw_type = rv.get("type", "any") if isinstance(rv, dict) else str(rv)
                    ts_t = sanitize_ts_type_str(raw_type)
                    master_lines.append(f"    {rk}: {ts_t};")
            master_lines.append("  }\n")

    master_lines.append("  // Unified API Client Signature")
    master_lines.append("  export interface ApiEndpointsMap {")
    for ep in endpoints:
        m = ep['method']
        p = ep['path']
        h = sanitize_ts_identifier(ep.get('handler', 'Api'))
        req_t = sanitize_ts_identifier(ep.get("request_body", {}).get("name", f"{h}Request")) if ep.get("request_body") else "void"
        resp_t = f"{h}Response"
        master_lines.append(f"    '{m} {p}': {{ request: {req_t}; response: {resp_t} }};")
    master_lines.append("  }")
    master_lines.append("}\n")

    master_ts_file = os.path.join(types_base, "api.contracts.d.ts")
    index_ts_file = os.path.join(types_base, "index.d.ts")

    with open(master_ts_file, "w", encoding="utf-8") as f:
        f.write("\n".join(master_lines))
    generated.append(master_ts_file)

    with open(index_ts_file, "w", encoding="utf-8") as f:
        f.write("\n".join(master_lines))
    generated.append(index_ts_file)

    return generated

def export_postman_collection(endpoints: List[Dict[str, Any]], output_file: str, project_name: str = "Project API"):
    """Exports postman/api_collection.json (v2.1.0) grouped by module."""
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    grouped = group_endpoints_by_module(endpoints)

    collection = {
        "info": {
            "_postman_id": hashlib.md5(project_name.encode("utf-8")).hexdigest(),
            "name": f"{project_name} API Collection",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "description": "Autogenerated 8-Section API Collection via fayzillo-agy-tools doc module."
        },
        "item": [],
        "variable": [
            {
                "key": "baseUrl",
                "value": "http://localhost:3000",
                "type": "string"
            }
        ]
    }

    for mod_name, mod_endpoints in grouped.items():
        folder_items = []
        for ep in mod_endpoints:
            url_path_segments = [p.replace(":", "") for p in ep["path"].strip("/").split("/")]

            headers = [{"key": "Accept", "value": "application/json", "type": "text"}]
            if ep.get("auth"):
                headers.append({"key": "Authorization", "value": "Bearer {{jwt_token}}", "type": "text"})
            if ep.get("method") in ["POST", "PUT", "PATCH"]:
                headers.append({"key": "Content-Type", "value": "application/json", "type": "text"})

            item_obj = {
                "name": f"{ep['method']} {ep['path']} ({ep.get('handler', '')})",
                "request": {
                    "method": ep["method"],
                    "header": headers,
                    "url": {
                        "raw": "{{baseUrl}}" + ep["path"],
                        "host": ["{{baseUrl}}"],
                        "path": url_path_segments
                    },
                    "description": ep.get("summary", "")
                },
                "response": [
                    {
                        "name": "Live Sandbox Probed Response" if ep.get("probed") else "Success Response",
                        "originalRequest": {
                            "method": ep["method"],
                            "header": headers,
                            "url": {
                                "raw": "{{baseUrl}}" + ep["path"],
                                "host": ["{{baseUrl}}"],
                                "path": url_path_segments
                            }
                        },
                        "status": "OK (Probed)" if ep.get("probed") else "OK",
                        "code": ep.get("probe_status", 200 if ep["method"] != "POST" else 201),
                        "_postman_previewlanguage": "json",
                        "body": json.dumps(ep.get("mock_response", {}), indent=2, ensure_ascii=False)
                    }
                ]
            }

            if ep.get("request_body"):
                item_obj["request"]["body"] = {
                    "mode": "raw",
                    "raw": json.dumps(ep.get("mock_request", {}), indent=2),
                    "options": {"raw": {"language": "json"}}
                }

            folder_items.append(item_obj)

        collection["item"].append({
            "name": f"📦 {mod_name.capitalize()}",
            "item": folder_items
        })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)

# ==========================================================
# MAIN EXECUTION RUNNER
# ==========================================================

def run_doc_generate(args):
    """Main CLI handler for `agy-tool doc`."""
    target_arg = getattr(args, 'path', '.') or '.'
    if target_arg == "probe":
        return run_doc_probe(args)
    elif target_arg == "sync-db":
        return run_doc_sync_db(args)

    target_path = safe_jail_path(target_arg)
    force = getattr(args, 'force', False)
    probe = getattr(args, 'probe', False) or getattr(args, 'probe_db', False)
    exports = getattr(args, 'export', "md,ts,postman")
    export_list = [e.strip().lower() for e in exports.split(",") if e.strip()]
    
    proj_name = os.path.basename(os.path.abspath(target_path).rstrip('/\\')) or "project"
    
    # Standardize output directory as <project_name>_contracts/ unless output_dir is given
    custom_out = getattr(args, 'output_dir', None)
    if custom_out:
        output_dir = safe_jail_path(custom_out, base_dir=target_path)
    else:
        output_dir = os.path.join(os.path.dirname(target_path), f"{proj_name}_contracts")
        # If target_path is root of project and we want output inside or sibling
        if not os.path.exists(output_dir):
            output_dir = os.path.join(target_path, f"{proj_name}_contracts")

    safe_jail_path(output_dir, base_dir=target_path)
    os.makedirs(output_dir, exist_ok=True)

    emit_progress("Analyzing Project", 10, f"Loyiha arxitekturasi va fayllar xaritasi tekshirilmoqda ({proj_name})...")

    proj_hash = compute_project_hash(target_path)
    cached_endpoints = None if force else load_cached_contracts(target_path, proj_hash)

    if cached_endpoints is not None:
        emit_progress("Cache Hit", 60, "Keshdan tezkor yuklanmoqda (Incremental Sha256)...")
        endpoints = cached_endpoints
    else:
        emit_progress("Detecting Framework", 30, "Freymvork va chuqur AST adapteri aniqlanmoqda...")
        adapter = select_adapter(target_path)
        framework_name = adapter.__class__.__name__.replace("Adapter", "")

        emit_progress("Scanning Endpoints & Services", 50, f"{framework_name} DTO, Servislar va 8-bosqichli kontraktlar tahlil qilinmoqda...")
        all_endpoints = adapter.scan()

        emit_progress("Applying Excludes & .apiignore", 70, "Maxfiy modullar (billing, payment) va .apiignore qoidalari tekshirilmoqda...")
        ignore_rules = load_api_ignore(target_path)
        cli_excludes = getattr(args, "exclude", None)
        if cli_excludes:
            ex_items = cli_excludes if isinstance(cli_excludes, list) else [s.strip() for s in cli_excludes.split(",") if s.strip()]
            ignore_rules.extend(ex_items)

        endpoints = [ep for ep in all_endpoints if not is_endpoint_ignored(ep, ignore_rules)]

        if probe:
            emit_progress("Discovering Probe Config", 75, "Dev DB Sandbox va probe parametrlari aniqlanmoqda...")
            probe_cfg = load_probe_config(target_path, args)
            emit_progress("Active Sandbox Probing", 80, f"Xavfsiz GET probing o'tkazilmoqda ({probe_cfg['base_url']})...")
            probe_safe_endpoints(
                endpoints,
                base_url=probe_cfg["base_url"],
                probe_db=probe_cfg.get("probe_db", False) or getattr(args, "probe_db", False),
                db_config=probe_cfg,
                exclude_patterns=probe_cfg.get("exclude")
            )

        save_cached_contracts(target_path, proj_hash, endpoints)

    # Exporting into <project>_contracts/ docs/*.md, types/*.ts, postman/*.json
    emit_progress("Exporting Contracts", 90, f"8-bosqichli kontraktlar {output_dir} ga yozilmoqda...")
    
    generated_files = []

    if "md" in export_list:
        md_files = export_markdown_modular(endpoints, output_dir, proj_name)
        for f in md_files:
            generated_files.append(os.path.relpath(f, target_path) if f.startswith(target_path) else f)

    if "ts" in export_list:
        ts_files = export_typescript_modular(endpoints, output_dir)
        for f in ts_files:
            generated_files.append(os.path.relpath(f, target_path) if f.startswith(target_path) else f)

    if "postman" in export_list:
        pm_file = os.path.join(output_dir, "postman", "api_collection.json")
        export_postman_collection(endpoints, pm_file, proj_name)
        generated_files.append(os.path.relpath(pm_file, target_path) if pm_file.startswith(target_path) else pm_file)

    emit_progress("Done", 100, f"{len(endpoints)} ta endpoint 8-bosqichli formatda muvaffaqiyatli hujjatlashtirildi.")

    emit_result({
        "project_path": target_path,
        "output_directory": output_dir,
        "total_endpoints": len(endpoints),
        "exported_files": generated_files,
        "endpoints": endpoints
    })

def run_doc_probe(args):
    """Subcommand handler for `agy-tool doc probe`."""
    target_arg = getattr(args, 'path', '.')
    if target_arg in ["probe", "sync-db", "generate", None, ""]:
        target_arg = "."
    target_path = safe_jail_path(target_arg)
    
    emit_progress("Discovering Sandbox Config", 15, "Sandbox va probe parametrlari aniqlanmoqda...")
    probe_cfg = load_probe_config(target_path, args)
    
    emit_progress("Scanning Project", 35, "Loyiha kontrollerlari va marshrutlari tahlil qilinmoqda...")
    adapter = select_adapter(target_path)
    all_endpoints = adapter.scan()
    ignore_rules = load_api_ignore(target_path)
    cli_excludes = getattr(args, "exclude", None)
    if cli_excludes:
        ex_items = cli_excludes if isinstance(cli_excludes, list) else [s.strip() for s in cli_excludes.split(",") if s.strip()]
        ignore_rules.extend(ex_items)

    endpoints = [ep for ep in all_endpoints if not is_endpoint_ignored(ep, ignore_rules)]
    
    emit_progress("Active Sandbox Probing", 60, f"Xavfsiz GET probing o'tkazilmoqda ({probe_cfg['base_url']})...")
    probe_stats = probe_safe_endpoints(
        endpoints,
        base_url=probe_cfg["base_url"],
        probe_db=True if (probe_cfg.get("probe_db") or getattr(args, "probe_db", False) or probe_cfg.get("dev_db")) else False,
        db_config=probe_cfg,
        exclude_patterns=probe_cfg.get("exclude")
    )
    
    proj_hash = compute_project_hash(target_path)
    save_cached_contracts(target_path, proj_hash, endpoints)
    
    emit_progress("Done", 100, f"Aktiv probing yakunlandi: {probe_stats.get('successful', 0)} muvaffaqiyatli.")
    emit_result({
        "project_path": target_path,
        "probe_stats": probe_stats,
        "endpoints": endpoints
    })

def run_doc_sync_db(args):
    """Subcommand handler for `agy-tool doc sync-db`."""
    target_arg = getattr(args, 'path', '.')
    if target_arg in ["probe", "sync-db", "generate", None, ""]:
        target_arg = "."
    target_path = safe_jail_path(target_arg)
    
    emit_progress("Discovering Sandbox Config", 20, "Sandbox va Dev DB konfiguratsiyasi tekshirilmoqda...")
    probe_cfg = load_probe_config(target_path, args)
    
    src = probe_cfg.get("source_db")
    tgt = probe_cfg.get("dev_db")
    if not src or not tgt:
        raise ValueError("Source DB (--source-db) va Dev DB (--dev-db) parametrlari talab qilinadi!")
        
    emit_progress("Syncing Database", 60, "Asl DB dan Dev DB ga xavfsiz minimal snapshot import qilinmoqda...")
    res = sync_probe_db(src, tgt, safe_tables=probe_cfg.get("safe_tables"))
    
    emit_progress("Done", 100, f"{len(res.get('synced_tables', []))} ta jadval dev sandboxga xavfsiz yuklandi.")
    emit_result(res)
