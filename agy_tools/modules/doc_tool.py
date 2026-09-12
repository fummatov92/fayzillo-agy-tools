import os
import sys
import re
import json
import hashlib
import fnmatch
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from agy_tools.utils import emit_progress, emit_result, safe_jail_path
from agy_tools.adapters.nestjs_adapter import NestJSAdapter
from agy_tools.adapters.express_adapter import ExpressAdapter
from agy_tools.adapters.go_adapter import GoAdapter
from agy_tools.adapters.laravel_adapter import LaravelAdapter

def get_doc_describe():
    return {
        "name": "doc",
        "description": "Multi-Framework Zero-Token API Kontrakt & DTO Generator (NestJS, Express, Go, Laravel).",
        "commands": {
            "generate": "Loyiha kontrollerlari va DTOlarini tahlil qilib, 3 xil formatda (Markdown, TS Types, Postman) API kontraktlarini generatsiya qilish",
            "probe": "Xavfsiz GET-only aktiv probing orqali tirik endpointlar sxemalarini boyitish"
        }
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
    full_sig = f"{method} {path}"

    for pat in ignore_patterns:
        pat = pat.strip()
        # Case 1: Pattern specifies method: "POST /billing/*"
        if " " in pat:
            p_method, p_path = pat.split(" ", 1)
            if p_method.upper() == method and fnmatch.fnmatch(path, p_path):
                return True
        # Case 2: Exact or glob path match: "/billing/*" or "*/webhooks/*"
        elif fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path, f"*{pat}*"):
            return True
        # Case 3: Simple keyword match: "payme", "click", "billing"
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
    cache_file = get_cache_path(project_path)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("hash") == current_hash and "endpoints" in data:
                    return data["endpoints"]
        except Exception:
            pass
    return None

def save_cached_contracts(project_path: str, current_hash: str, endpoints: List[Dict[str, Any]]):
    cache_file = get_cache_path(project_path)
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"hash": current_hash, "project": project_path, "endpoints": endpoints}, f)
    except Exception:
        pass

def select_adapter(project_path: str):
    """Detects and returns the best matching framework adapter."""
    adapters = [
        NestJSAdapter(project_path),
        ExpressAdapter(project_path),
        GoAdapter(project_path),
        LaravelAdapter(project_path)
    ]
    for ad in adapters:
        if ad.detect():
            return ad
    # Default fallback to Express/JS parser
    return ExpressAdapter(project_path)

def probe_safe_endpoints(endpoints: List[Dict[str, Any]], base_url: str = "http://127.0.0.1:3000"):
    """Active Probing: Safely checks GET-only idempotent endpoints with short timeout."""
    for ep in endpoints:
        if ep.get("method") == "GET" and ":" not in ep.get("path", "") and "{" not in ep.get("path", ""):
            url = base_url.rstrip("/") + ep.get("path", "")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "agy-tool-probe"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        body_raw = resp.read().decode("utf-8")
                        data = json.loads(body_raw)
                        ep["probed"] = True
                        ep["probe_status"] = 200
                        # Enrich mock response with live probed payload if valid dict
                        if isinstance(data, dict):
                            ep["mock_response"] = data
            except Exception:
                ep["probed"] = False

# ==========================================================
# 3-WAY SYNCHRONIZED EXPORTERS
# ==========================================================

def export_markdown_contracts(endpoints: List[Dict[str, Any]], output_file: str, project_name: str = "API"):
    """Exports docs/api_contracts.md."""
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    
    lines = []
    lines.append(f"# 📘 API Contracts Specification — {project_name}")
    lines.append(f"\n> **Autogenerated by `agy-tool doc`** | Zero-Token High-Speed Schema Extraction\n")
    lines.append(f"**Jami API Endpointlari:** {len(endpoints)} ta\n")
    lines.append("## 📑 Mundarija (Table of Contents)\n")

    for i, ep in enumerate(endpoints, 1):
        m = ep['method']
        p = ep['path']
        anchor = f"{m.lower()}-{p.replace('/', '').replace(':', '').replace('{', '').replace('}', '').lower()}"
        lines.append(f"{i}. [`{m}` **{p}**](#{anchor}) — {ep.get('summary', '')}")

    lines.append("\n---\n")

    for ep in endpoints:
        m = ep['method']
        p = ep['path']
        anchor = f"{m.lower()}-{p.replace('/', '').replace(':', '').replace('{', '').replace('}', '').lower()}"
        
        badge_color = "blue"
        if m == "GET": badge_color = "green"
        elif m == "POST": badge_color = "blue"
        elif m in ["PUT", "PATCH"]: badge_color = "orange"
        elif m == "DELETE": badge_color = "red"

        lines.append(f"### <a id=\"{anchor}\"></a>`{m}` {p}\n")
        lines.append(f"- **Handler:** `{ep.get('handler', 'N/A')}`")
        lines.append(f"- **Fayl:** `{ep.get('file', '')}:{ep.get('line', 1)}`")
        lines.append(f"- **Autentifikatsiya:** `{'🔒 Majburiy (Bearer/Guard)' if ep.get('auth') else '🔓 Ochiq (Public)'}`")
        
        # Headers & Params
        if ep.get("params"):
            lines.append("\n#### 🎯 URL Parametrlari (Path Params):")
            lines.append("| Parametr | Tip | Majburiy |")
            lines.append("|---|---|---|")
            for param in ep["params"]:
                lines.append(f"| `{param['name']}` | `{param.get('type', 'string')}` | `{'Ha' if param.get('required') else 'Yoq'}` |")

        if ep.get("query"):
            lines.append("\n#### 🔍 Query Parametrlari:")
            lines.append("| Parametr | Tip | Majburiy |")
            lines.append("|---|---|---|")
            for q in ep["query"]:
                lines.append(f"| `{q['name']}` | `{q.get('type', 'string')}` | `{'Ha' if q.get('required') else 'Yoq'}` |")

        # Request Body
        if ep.get("request_body"):
            rb = ep["request_body"]
            lines.append(f"\n#### 📥 Request Body (`{rb.get('name', 'RequestBody')}`):")
            if rb.get("properties"):
                lines.append("| Maydon | Tip | Majburiy | Qo'shimcha cheklovlar |")
                lines.append("|---|---|---|---|")
                for k, v in rb["properties"].items():
                    req_str = "Ha" if v.get("required") else "Yo'q"
                    extra = []
                    if "min" in v: extra.append(f"min: {v['min']}")
                    if "max" in v: extra.append(f"max: {v['max']}")
                    if "format" in v: extra.append(f"format: {v['format']}")
                    if "enum" in v: extra.append(f"enum: {v['enum']}")
                    lines.append(f"| `{k}` | `{v.get('type', 'string')}` | `{req_str}` | `{', '.join(extra) if extra else '-'}` |")

            lines.append("\n**Request Mock JSON:**")
            lines.append("```json")
            lines.append(json.dumps(ep.get("mock_request", {}), indent=2, ensure_ascii=False))
            lines.append("```")

        # Response
        lines.append("\n#### 📤 Response (Kutilgan javob):")
        lines.append("```json")
        lines.append(json.dumps(ep.get("mock_response", {}), indent=2, ensure_ascii=False))
        lines.append("```\n")
        lines.append("---\n")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

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
    # Remove hyphens from custom types
    if "-" in t:
        parts = re.split(r"[-_\s]+", t)
        return "".join(p.capitalize() for p in parts if p)
    return t

def export_typescript_dtos(endpoints: List[Dict[str, Any]], output_file: str):
    """Exports types/api.contracts.d.ts."""
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    
    lines = []
    lines.append("/* eslint-disable */")
    lines.append("/**")
    lines.append(" * Autogenerated TypeScript DTO Contracts by agy-tool doc.")
    lines.append(" * Zero-Token Synchronized Types Definition.")
    lines.append(" */\n")
    lines.append("export namespace ApiContracts {")

    generated_types = set()

    for ep in endpoints:
        m = ep['method']
        p = ep['path']
        handler_clean = sanitize_ts_identifier(ep.get('handler', 'Api'))

        # Request DTO
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

        # Response DTO
        resp_name = f"{handler_clean}Response"
        if resp_name not in generated_types:
            generated_types.add(resp_name)
            lines.append(f"  export interface {resp_name} {{")
            resp_schema = ep.get("response", {})
            for rk, rv in resp_schema.get("properties", {}).items():
                raw_type = rv.get("type", "any") if isinstance(rv, dict) else str(rv)
                ts_t = sanitize_ts_type_str(raw_type)
                lines.append(f"    {rk}: {ts_t};")
            lines.append("  }\n")

    lines.append("  // Unified API Client Signature")
    lines.append("  export interface ApiEndpointsMap {")
    for ep in endpoints:
        m = ep['method']
        p = ep['path']
        h = sanitize_ts_identifier(ep.get('handler', 'Api'))
        req_t = sanitize_ts_identifier(ep.get("request_body", {}).get("name", f"{h}Request")) if ep.get("request_body") else "void"
        resp_t = f"{h}Response"
        lines.append(f"    '{m} {p}': {{ request: {req_t}; response: {resp_t} }};")
    lines.append("  }")
    lines.append("}\n")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def export_postman_collection(endpoints: List[Dict[str, Any]], output_file: str, project_name: str = "Project API"):
    """Exports postman/api_collection.json (v2.1.0)."""
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    
    collection = {
        "info": {
            "_postman_id": hashlib.md5(project_name.encode("utf-8")).hexdigest(),
            "name": f"{project_name} API Collection",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "description": "Autogenerated API Collection via fayzillo-agy-tools doc module."
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

    # Group endpoints by resource folder
    folders: Dict[str, List[Dict[str, Any]]] = {}

    for ep in endpoints:
        path_parts = [p for p in ep["path"].split("/") if p and not p.startswith("api")]
        folder_name = path_parts[0].capitalize() if path_parts else "General"
        if folder_name not in folders:
            folders[folder_name] = []
        folders[folder_name].append(ep)

    for folder_name, folder_eps in folders.items():
        folder_items = []
        for ep in folder_eps:
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
                        "name": "Success Response",
                        "originalRequest": {
                            "method": ep["method"],
                            "header": headers,
                            "url": {
                                "raw": "{{baseUrl}}" + ep["path"],
                                "host": ["{{baseUrl}}"],
                                "path": url_path_segments
                            }
                        },
                        "status": "OK",
                        "code": 200 if ep["method"] != "POST" else 201,
                        "_postman_previewlanguage": "json",
                        "body": json.dumps(ep.get("mock_response", {}), indent=2)
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
            "name": folder_name,
            "item": folder_items
        })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)


# ==========================================================
# MAIN EXECUTION RUNNER
# ==========================================================

def run_doc_generate(args):
    """Main CLI handler for `agy-tool doc`."""
    target_path = safe_jail_path(args.path if hasattr(args, 'path') and args.path else ".")
    force = getattr(args, 'force', False)
    probe = getattr(args, 'probe', False)
    exports = getattr(args, 'export', "md,ts,postman")
    export_list = [e.strip().lower() for e in exports.split(",") if e.strip()]
    output_dir = getattr(args, 'output_dir', None) or target_path

    emit_progress("Analyzing Project", 10, "Loyiha arxitekturasi va fayllar xaritasi tekshirilmoqda...")

    proj_hash = compute_project_hash(target_path)
    cached_endpoints = None if force else load_cached_contracts(target_path, proj_hash)

    if cached_endpoints is not None:
        emit_progress("Cache Hit", 60, "Keshdan tezkor yuklanmoqda (Incremental Sha256)...")
        endpoints = cached_endpoints
    else:
        emit_progress("Detecting Framework", 30, "Freymvork va adapter aniqlanmoqda...")
        adapter = select_adapter(target_path)
        framework_name = adapter.__class__.__name__.replace("Adapter", "")

        emit_progress("Scanning Endpoints & DTOs", 50, f"{framework_name} DTO va marshrutlari tahlil qilinmoqda...")
        all_endpoints = adapter.scan()

        emit_progress("Applying .apiignore", 70, ".apiignore qoidalari tekshirilmoqda...")
        ignore_rules = load_api_ignore(target_path)
        endpoints = [ep for ep in all_endpoints if not is_endpoint_ignored(ep, ignore_rules)]

        if probe:
            emit_progress("Active Probing", 80, "Tirik lokal serverda xavfsiz GET probing o'tkazilmoqda...")
            probe_safe_endpoints(endpoints)

        save_cached_contracts(target_path, proj_hash, endpoints)

    # Exporting
    emit_progress("Exporting Contracts", 90, "Hujjatlar (MD, TS, Postman) shakllantirilmoqda...")
    
    generated_files = []
    proj_name = os.path.basename(os.path.abspath(target_path))

    if "md" in export_list:
        md_file = os.path.join(output_dir, "docs", "api_contracts.md")
        export_markdown_contracts(endpoints, md_file, proj_name)
        generated_files.append(os.path.relpath(md_file, target_path) if md_file.startswith(target_path) else md_file)

    if "ts" in export_list:
        ts_file = os.path.join(output_dir, "types", "api.contracts.d.ts")
        export_typescript_dtos(endpoints, ts_file)
        generated_files.append(os.path.relpath(ts_file, target_path) if ts_file.startswith(target_path) else ts_file)

    if "postman" in export_list:
        pm_file = os.path.join(output_dir, "postman", "api_collection.json")
        export_postman_collection(endpoints, pm_file, proj_name)
        generated_files.append(os.path.relpath(pm_file, target_path) if pm_file.startswith(target_path) else pm_file)

    emit_progress("Done", 100, f"{len(endpoints)} ta endpoint muvaffaqiyatli hujjatlashtirildi.")

    emit_result({
        "project_path": target_path,
        "total_endpoints": len(endpoints),
        "exported_files": generated_files,
        "endpoints": endpoints
    })
