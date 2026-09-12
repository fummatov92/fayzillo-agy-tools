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

def scan_nestjs_endpoints(src_dir: str) -> list:
    """Scan NestJS controllers using regex pattern matching."""
    endpoints = []
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
                            
                            full_path = "/" + "/".join(filter(None, [base_route.strip("/"), sub_path.strip("/")]))
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

def scan_express_endpoints(src_dir: str) -> list:
    """Scan Express routes."""
    endpoints = []
    express_regex = re.compile(r"(?:app|router)\.(get|post|put|delete|patch)\((?:['\"]([^'\"]+)['\"])", re.IGNORECASE)
    
    for root, _, files in os.walk(src_dir):
        if "node_modules" in root or ".git" in root or "dist" in root or ".angular" in root:
            continue
        for file in files:
            if file.endswith((".js", ".ts")) and not file.endswith(".d.ts"):
                filepath = os.path.join(root, file)
                relpath = os.path.relpath(filepath, src_dir)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f):
                            m = express_regex.search(line)
                            if m:
                                endpoints.append({
                                    "method": m.group(1).upper(),
                                    "path": m.group(2),
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
