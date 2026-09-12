import os
import sys
import re
import json
from pathlib import Path
from agy_tools.utils import emit_progress, emit_result, safe_jail_path

def get_code_describe():
    return {
        "name": "code",
        "description": "Loyiha arxitekturasi, modullari, API endpointlari va kontrollerlarini AST/Regex yordamida tezkor digest shaklida chiqarish.",
        "commands": {
            "blueprint": "Loyiha umumiy tuzilishi, ishlatilgan freymvork va asosiy fayllar xaritasi",
            "endpoints": "NestJS / Express / FastAPI / Django loyihalaridagi barcha marshrutlar (routes/endpoints)",
            "symbols": "Fayl yoki papkadagi barcha class va funksiyalar signaturalari"
        }
    }

def detect_framework(project_path: str) -> dict:
    """Detect tech stack and framework by reading config files."""
    info = {"type": "Unknown", "language": "Unknown", "entry_points": []}
    
    pkg_json = os.path.join(project_path, "package.json")
    if os.path.exists(pkg_json):
        try:
            with open(pkg_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                
                # Check angular first or nestjs before general express
                if "@angular/core" in deps or "angular" in str(deps):
                    info["type"] = "Angular"
                elif "@nestjs/core" in deps:
                    info["type"] = "NestJS"
                elif "react" in deps or "next" in deps:
                    info["type"] = "React / Next.js"
                elif "express" in deps:
                    info["type"] = "Express"
                else:
                    info["type"] = "Node.js"
                info["language"] = "TypeScript" if ("typescript" in deps or os.path.exists(os.path.join(project_path, "tsconfig.json"))) else "JavaScript"
                info["main"] = data.get("main", "")
        except Exception:
            pass
            
    pyproject = os.path.join(project_path, "pyproject.toml")
    req_txt = os.path.join(project_path, "requirements.txt")
    if os.path.exists(pyproject) or os.path.exists(req_txt):
        info["language"] = "Python"
        content = ""
        if os.path.exists(req_txt):
            try:
                with open(req_txt, "r") as f:
                    content += f.read().lower()
            except Exception:
                pass
        if "fastapi" in content:
            info["type"] = "FastAPI"
        elif "django" in content:
            info["type"] = "Django"
        elif "flask" in content:
            info["type"] = "Flask"
        else:
            info["type"] = "Python App"
            
    return info

def _find_nestjs_global_prefix(src_dir: str) -> str:
    """Discovers global prefix from main.ts / bootstrap files."""
    candidate_files = [
        "src/main.ts", "src/main.js", "main.ts", "main.js",
        "src/bootstrap.ts", "src/bootstrap.js", "src/index.ts", "src/index.js",
        "src/app.ts", "src/app.js", "src/server.ts", "src/server.js"
    ]
    found_files = []
    for rel in candidate_files:
        p = os.path.join(src_dir, rel)
        if os.path.exists(p):
            found_files.append(p)
            
    if not found_files:
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build", ".next", ".angular"]]
            for file in files:
                if file.endswith((".ts", ".js")) and not file.endswith((".dto.ts", ".controller.ts", ".service.ts", ".module.ts", ".spec.ts", ".d.ts")):
                    found_files.append(os.path.join(root, file))

    for fpath in found_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            match = re.search(r"(?:app|server)\.setGlobalPrefix\s*\(\s*([^,\)]+)", content)
            if match:
                raw_arg = match.group(1).strip()
                str_match = re.match(r"^['\"`]([^'\"`]+)['\"`]$", raw_arg)
                if str_match:
                    return str_match.group(1).strip("/")
                str_in_expr = re.search(r"['\"`]([^'\"`]+)['\"`]", raw_arg)
                if str_in_expr:
                    return str_in_expr.group(1).strip("/")
                var_name = raw_arg.strip()
                if re.match(r"^[A-Za-z0-9_$]+$", var_name):
                    var_def = re.search(r"(?:const|let|var)\s+" + re.escape(var_name) + r"\s*=\s*([^;\n]+)", content)
                    if var_def:
                        val_expr = var_def.group(1)
                        val_str_match = re.search(r"['\"`]([^'\"`]+)['\"`]", val_expr)
                        if val_str_match:
                            return val_str_match.group(1).strip("/")
        except Exception:
            pass
    return ""

def scan_nestjs_endpoints(src_dir: str) -> list:
    """Scan NestJS controllers using regex pattern matching."""
    endpoints = []
    global_prefix = _find_nestjs_global_prefix(src_dir)
    controller_regex = re.compile(r"@Controller\((?:['\"]([^'\"]*)['\"])?\)")
    method_regex = re.compile(r"@(Get|Post|Put|Delete|Patch|Options|Head)\((?:['\"]([^'\"]*)['\"])?\)")
    func_regex = re.compile(r"(?:async\s+)?([a-zA-Z0-9_]+)\s*\(")
    RESERVED_WORDS = {"constructor", "if", "for", "while", "switch", "return", "catch", "try"}
    
    for root, _, files in os.walk(src_dir):
        if "node_modules" in root or ".git" in root or "dist" in root or ".angular" in root:
            continue
        for file in files:
            if file.endswith(".controller.ts") or file.endswith(".controller.js"):
                filepath = os.path.join(root, file)
                relpath = os.path.relpath(filepath, src_dir)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    
                    base_route = ""
                    for i, line in enumerate(lines):
                        ctrl_match = controller_regex.search(line)
                        if ctrl_match:
                            base_route = ctrl_match.group(1) or ""
                        
                        m_match = method_regex.search(line)
                        if m_match:
                            http_verb = m_match.group(1).upper()
                            sub_path = m_match.group(2) or ""
                            
                            # Find following function name (skip decorators like @Roles, @ApiBearerAuth, @HttpCode)
                            func_name = "handler"
                            for next_line in lines[i+1:min(i+12, len(lines))]:
                                trimmed = next_line.strip()
                                if trimmed.startswith("@") or trimmed.startswith("//") or not trimmed:
                                    continue
                                f_match = func_regex.search(next_line)
                                if f_match and f_match.group(1) not in RESERVED_WORDS:
                                    func_name = f_match.group(1)
                                    break
                            
                            clean_base = base_route.strip("/")
                            clean_sub = sub_path.strip("/")
                            clean_global = global_prefix.strip("/")

                            if clean_global:
                                if clean_base == clean_global or clean_base.startswith(clean_global + "/"):
                                    raw_parts = [clean_base, clean_sub]
                                else:
                                    raw_parts = [clean_global, clean_base, clean_sub]
                            else:
                                raw_parts = [clean_base, clean_sub]

                            full_path = "/" + "/".join(filter(None, raw_parts))
                            endpoints.append({
                                "method": http_verb,
                                "path": full_path,
                                "handler": func_name,
                                "file": relpath,
                                "line": i + 1
                            })
                except Exception:
                    pass
    return endpoints

def _build_express_mount_map(src_dir: str) -> dict:
    """Builds a router mount map for Express code scan."""
    file_imports = {}
    raw_mounts = []

    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build", ".next", ".angular"]]
        for file in files:
            if not file.endswith((".js", ".ts", ".mjs", ".cjs")) or file.endswith(".d.ts"):
                continue
            filepath = os.path.join(root, file)
            rel_file = os.path.normpath(os.path.relpath(filepath, src_dir))
            file_dir = os.path.dirname(rel_file)

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue

            current_imports = {}
            req_matches = re.finditer(
                r"(?:const|let|var)\s+(?:\{\s*(?:[A-Za-z0-9_$]+\s*:\s*)?([A-Za-z0-9_$]+)\s*\}|([A-Za-z0-9_$]+))\s*=\s*require\(\s*['\"`]([^'\"`]+)['\"`]\s*\)",
                content
            )
            for m in req_matches:
                var_name = m.group(1) or m.group(2)
                imp_path = m.group(3).strip()
                if imp_path.startswith("."):
                    target_rel = os.path.normpath(os.path.join(file_dir, imp_path))
                    current_imports[var_name] = target_rel

            imp_matches = re.finditer(
                r"import\s+(?:(?:\*\s+as\s+)?([A-Za-z0-9_$]+)|\{\s*(?:[A-Za-z0-9_$]+\s+as\s+)?([A-Za-z0-9_$]+)\s*\})\s+from\s+['\"`]([^'\"`]+)['\"`]",
                content
            )
            for m in imp_matches:
                var_name = m.group(1) or m.group(2)
                imp_path = m.group(3).strip()
                if imp_path.startswith("."):
                    target_rel = os.path.normpath(os.path.join(file_dir, imp_path))
                    current_imports[var_name] = target_rel

            file_imports[rel_file] = current_imports

            use_matches = re.finditer(
                r"(?:app|router|server)\.use\(\s*['\"`]([^'\"`]+)['\"`]\s*,\s*(.*?)\)",
                content,
                re.DOTALL
            )
            for m in use_matches:
                mount_path = m.group(1).strip()
                args_part = m.group(2)
                inline_req = re.search(r"require\(\s*['\"`]([^'\"`]+)['\"`]\s*\)", args_part)
                if inline_req:
                    imp_path = inline_req.group(1).strip()
                    if imp_path.startswith("."):
                        target_rel = os.path.normpath(os.path.join(file_dir, imp_path))
                        raw_mounts.append((rel_file, mount_path, target_rel))
                else:
                    for var_name, target_rel in current_imports.items():
                        if re.search(rf"\b{re.escape(var_name)}\b", args_part):
                            raw_mounts.append((rel_file, mount_path, target_rel))

    mount_map = {}
    def register_aliases(target_rel: str, prefix: str):
        clean_p = "/" + prefix.strip("/") if prefix.strip("/") else ""
        norm_tgt = os.path.normpath(target_rel)
        mount_map[norm_tgt] = clean_p
        base_no_ext, ext = os.path.splitext(norm_tgt)
        mount_map[base_no_ext] = clean_p
        for candidate_ext in [".js", ".ts", ".mjs", ".cjs"]:
            mount_map[base_no_ext + candidate_ext] = clean_p
        mount_map[os.path.normpath(os.path.join(norm_tgt, "index.js"))] = clean_p
        mount_map[os.path.normpath(os.path.join(norm_tgt, "index.ts"))] = clean_p
        mount_map[os.path.normpath(os.path.join(base_no_ext, "index.js"))] = clean_p
        mount_map[os.path.normpath(os.path.join(base_no_ext, "index.ts"))] = clean_p

    for _ in range(3):
        for rel_file, mount_path, target_rel in raw_mounts:
            parent_prefix = mount_map.get(rel_file, "")
            combined_prefix = "/" + "/".join(filter(None, [parent_prefix.strip("/"), mount_path.strip("/")]))
            register_aliases(target_rel, combined_prefix)

    return mount_map

def scan_express_endpoints(src_dir: str) -> list:
    """Scan Express routes."""
    endpoints = []
    mount_map = _build_express_mount_map(src_dir)
    express_regex = re.compile(r"(?:app|router)\.(get|post|put|delete|patch)\((?:['\"]([^'\"]+)['\"])", re.IGNORECASE)
    
    for root, _, files in os.walk(src_dir):
        if "node_modules" in root or ".git" in root or "dist" in root or ".angular" in root:
            continue
        for file in files:
            if file.endswith((".js", ".ts", ".mjs", ".cjs")) and not file.endswith(".d.ts"):
                filepath = os.path.join(root, file)
                relpath = os.path.relpath(filepath, src_dir)
                norm_rel = os.path.normpath(relpath)
                mount_prefix = mount_map.get(norm_rel, "")
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f):
                            m = express_regex.search(line)
                            if m:
                                route_path = m.group(2)
                                clean_mount = mount_prefix.strip("/")
                                clean_route = route_path.strip("/")
                                if clean_mount:
                                    if clean_route == clean_mount or clean_route.startswith(clean_mount + "/"):
                                        full_path = "/" + clean_route
                                    else:
                                        full_path = "/" + "/".join(filter(None, [clean_mount, clean_route]))
                                else:
                                    full_path = "/" + clean_route

                                endpoints.append({
                                    "method": m.group(1).upper(),
                                    "path": full_path,
                                    "file": relpath,
                                    "line": i + 1
                                })
                except Exception:
                    pass
    return endpoints

def run_code_endpoints(args):
    """List all API endpoints/routes in the target codebase without reading all files."""
    emit_progress("Analyzing Codebase", 20, "Loyihani xavfsiz tekshirish...")
    target_path = safe_jail_path(args.path if hasattr(args, 'path') and args.path else ".")
    
    emit_progress("Detecting Framework", 40, "Freymvork aniqlanmoqda...")
    meta = detect_framework(target_path)
    
    endpoints = []
    emit_progress("Scanning Routes", 70, f"{meta['type']} marshrutlari tahlil qilinmoqda...")
    
    if meta["type"] == "NestJS":
        endpoints = scan_nestjs_endpoints(target_path)
    else:
        # Fallback to general express / router pattern scan
        endpoints = scan_express_endpoints(target_path)
        
    emit_progress("Done", 100, f"{len(endpoints)} ta endpoint topildi.")
    emit_result({
        "project_path": target_path,
        "framework": meta,
        "total_endpoints": len(endpoints),
        "endpoints": endpoints
    })

def run_code_blueprint(args):
    """Generate high-level architecture blueprint of a project."""
    emit_progress("Blueprint Generation", 15, "Fayllar daraxti tahlili...")
    target_path = safe_jail_path(args.path if hasattr(args, 'path') and args.path else ".")
    meta = detect_framework(target_path)
    
    configs = []
    key_files = []
    
    for root, dirs, files in os.walk(target_path):
        # Ignore junk & cache
        dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build", ".next", "__pycache__", ".agents", ".angular"]]
        rel_root = os.path.relpath(root, target_path)
        
        for file in files:
            rel_file = os.path.normpath(os.path.join(rel_root, file))
            if file in ["package.json", "tsconfig.json", "nest-cli.json", "angular.json", "Dockerfile", "docker-compose.yml", "schema.prisma"]:
                configs.append(rel_file)
            elif file.endswith((".module.ts", ".service.ts", ".controller.ts", ".resolver.ts", ".routes.ts", "main.ts", "app.ts", ".component.ts")):
                key_files.append(rel_file)
                
    emit_progress("Done", 100, "Loyiha arxitekturasi tayyor.")
    emit_result({
        "project_path": target_path,
        "framework": meta,
        "config_files": configs,
        "core_components_count": len(key_files),
        "key_components": key_files[:50]
    })
