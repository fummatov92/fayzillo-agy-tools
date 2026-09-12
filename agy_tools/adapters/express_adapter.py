import os
import re
import json
from typing import List, Dict, Any, Optional
from agy_tools.adapters.base_adapter import BaseAdapter

class ExpressAdapter(BaseAdapter):
    """Zero-token parser for Express & Next.js routes and Zod schemas."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self.zod_schemas: Dict[str, Dict[str, Any]] = {}
        self._parsed_schemas = False

    def detect(self) -> bool:
        pkg_json = os.path.join(self.project_path, "package.json")
        if os.path.exists(pkg_json):
            try:
                with open(pkg_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    return "express" in deps or "next" in deps or "koa" in deps or "fastify" in deps
            except Exception:
                pass
        return False

    def _parse_zod_schemas(self):
        """Scan TypeScript/JavaScript files for Zod object schemas."""
        zod_obj_pattern = re.compile(r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*z\.object\(\{([^}]+)\}\)")
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build", ".next", ".angular"]]
            for file in files:
                if file.endswith((".ts", ".js", ".mjs")):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()

                        for match in zod_obj_pattern.finditer(content):
                            schema_name = match.group(1)
                            raw_body = match.group(2)
                            props = self._parse_zod_body(raw_body)
                            self.zod_schemas[schema_name] = {
                                "name": schema_name,
                                "properties": props,
                                "file": os.path.relpath(filepath, self.project_path)
                            }
                    except Exception:
                        pass

    def _parse_zod_body(self, body: str) -> Dict[str, Any]:
        """Parses inner properties of z.object({ ... })."""
        props = {}
        for line in body.strip().split("\n"):
            line = line.strip().rstrip(",")
            if not line or line.startswith("//"):
                continue
            if ":" in line:
                key, z_chain = line.split(":", 1)
                key = key.strip().strip("'\"")
                z_chain = z_chain.strip()

                is_opt = ".optional()" in z_chain or ".nullable()" in z_chain
                p_type = "string"
                p_meta = {"required": not is_opt}

                if "z.string()" in z_chain:
                    p_type = "string"
                    if ".email()" in z_chain:
                        p_meta["format"] = "email"
                    if ".uuid()" in z_chain:
                        p_meta["format"] = "uuid"
                elif "z.number()" in z_chain:
                    p_type = "number"
                elif "z.boolean()" in z_chain:
                    p_type = "boolean"
                elif "z.array(" in z_chain:
                    p_type = "array"
                elif "z.enum(" in z_chain:
                    p_type = "string"
                    enum_m = re.search(r"z\.enum\(\[([^\]]+)\]\)", z_chain)
                    if enum_m:
                        p_meta["enum"] = [x.strip().strip("'\"") for x in enum_m.group(1).split(",")]

                min_m = re.search(r"\.min\((\d+)\)", z_chain)
                if min_m:
                    p_meta["min"] = int(min_m.group(1))
                max_m = re.search(r"\.max\((\d+)\)", z_chain)
                if max_m:
                    p_meta["max"] = int(max_m.group(1))

                p_meta["type"] = p_type
                props[key] = p_meta

        return props

    def scan(self) -> List[Dict[str, Any]]:
        if not self._parsed_schemas:
            self._parse_zod_schemas()
            self._parsed_schemas = True

        endpoints = []
        express_route_regex = re.compile(r"(?:app|router)\.(get|post|put|delete|patch)\((?:['\"]([^'\"]+)['\"])", re.IGNORECASE)
        next_app_methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]

        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build", ".next", ".angular"]]
            for file in files:
                filepath = os.path.join(root, file)
                relpath = os.path.relpath(filepath, self.project_path)

                # 1. Next.js App Router (app/api/**/route.ts)
                if ("app/api/" in relpath or "app/api\\" in relpath) and file in ["route.ts", "route.js"]:
                    api_sub = relpath.split("app/api/")[1].rsplit("/route.", 1)[0]
                    api_sub = api_sub.replace("[", ":").replace("]", "")
                    full_path = "/api/" + api_sub.strip("/")
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                        
                        for m_verb in next_app_methods:
                            if re.search(rf"export\s+async\s+function\s+{m_verb}\b", content):
                                schema = self._find_associated_zod_schema(content)
                                ep = self._create_endpoint(m_verb, full_path, m_verb.lower(), relpath, 1, schema)
                                endpoints.append(ep)
                    except Exception:
                        pass
                    continue

                # 2. Next.js Pages Router (pages/api/**/*.ts)
                if ("pages/api/" in relpath or "pages/api\\" in relpath) and file.endswith((".ts", ".js")) and not file.startswith("_"):
                    api_sub = relpath.split("pages/api/")[1].rsplit(".", 1)[0]
                    api_sub = api_sub.replace("[", ":").replace("]", "")
                    if api_sub.endswith("/index"):
                        api_sub = api_sub[:-6]
                    full_path = "/api/" + api_sub.strip("/")
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                        schema = self._find_associated_zod_schema(content)
                        # Check methods checked in handler
                        methods = []
                        for verb in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                            if f"req.method === '{verb}'" in content or f'req.method === "{verb}"' in content:
                                methods.append(verb)
                        if not methods:
                            methods = ["GET", "POST"]
                        for m_verb in methods:
                            ep = self._create_endpoint(m_verb, full_path, "handler", relpath, 1, schema)
                            endpoints.append(ep)
                    except Exception:
                        pass
                    continue

                # 3. Standard Express router files
                if file.endswith((".ts", ".js", ".mjs")) and not file.endswith(".d.ts"):
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            lines = f.readlines()

                        file_content = "".join(lines)
                        associated_schema = self._find_associated_zod_schema(file_content)

                        for i, line in enumerate(lines):
                            m = express_route_regex.search(line)
                            if m:
                                verb = m.group(1).upper()
                                route_path = m.group(2)
                                ep = self._create_endpoint(verb, route_path, f"{verb.lower()}_{i+1}", relpath, i + 1, associated_schema)
                                endpoints.append(ep)
                    except Exception:
                        pass

        return endpoints

    def _find_associated_zod_schema(self, content: str) -> Optional[Dict[str, Any]]:
        for schema_name, s_meta in self.zod_schemas.items():
            if schema_name in content:
                return {
                    "type": "object",
                    "name": schema_name,
                    "properties": s_meta["properties"]
                }
        return None

    def _create_endpoint(self, method: str, path: str, handler: str, file: str, line: int, schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        params = []
        param_names = re.findall(r":([a-zA-Z0-9_]+)", path)
        for pn in param_names:
            params.append({"name": pn, "type": "string", "required": True})

        req_body = schema if method in ["POST", "PUT", "PATCH"] else None
        
        # Heuristic response
        resp_props = {
            "success": {"type": "boolean", "required": True},
            "data": {"type": "object", "required": True, "properties": {"id": {"type": "string"}}}
        }
        resp_schema = {
            "status": 201 if method == "POST" else 200,
            "type": "object",
            "properties": resp_props
        }

        return {
            "method": method,
            "path": path,
            "handler": handler,
            "summary": f"{method} {path} endpoint",
            "auth": "/auth" in path or "/admin" in path,
            "headers": [{"name": "Content-Type", "type": "string", "required": True, "default": "application/json"}] if method in ["POST", "PUT", "PATCH"] else [],
            "params": params,
            "query": [],
            "request_body": req_body,
            "response": resp_schema,
            "mock_request": BaseAdapter.build_mock_from_schema(req_body),
            "mock_response": BaseAdapter.build_mock_from_schema(resp_schema),
            "file": file,
            "line": line
        }
