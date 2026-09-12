import os
import re
import json
from typing import List, Dict, Any, Optional
from agy_tools.adapters.base_adapter import BaseAdapter

class LaravelAdapter(BaseAdapter):
    """Zero-token parser for Laravel routes/api.php, FormRequest rules, and Resources."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self.form_requests: Dict[str, Dict[str, Any]] = {}
        self._parsed_requests = False

    def detect(self) -> bool:
        if os.path.exists(os.path.join(self.project_path, "artisan")):
            return True
        composer_json = os.path.join(self.project_path, "composer.json")
        if os.path.exists(composer_json):
            try:
                with open(composer_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    reqs = {**data.get("require", {}), **data.get("require-dev", {})}
                    return "laravel/framework" in reqs
            except Exception:
                pass
        return False

    def _parse_form_requests(self):
        """Scan app/Http/Requests for FormRequest classes and rules() method."""
        req_dir = os.path.join(self.project_path, "app", "Http", "Requests")
        if not os.path.exists(req_dir):
            return

        for root, _, files in os.walk(req_dir):
            for file in files:
                if file.endswith(".php"):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()

                        class_m = re.search(r"class\s+([A-Za-z0-9_]+)\s+extends\s+FormRequest", content)
                        rules_m = re.search(r"function\s+rules\s*\(\s*\)[^{]*\{([^}]+)\}", content)
                        if class_m and rules_m:
                            class_name = class_m.group(1)
                            rules_body = rules_m.group(1)
                            props = self._parse_rules_body(rules_body)
                            self.form_requests[class_name] = {
                                "name": class_name,
                                "properties": props,
                                "file": os.path.relpath(filepath, self.project_path)
                            }
                    except Exception:
                        pass

    def _parse_rules_body(self, body: str) -> Dict[str, Any]:
        props = {}
        # Matches 'title' => 'required|string|max:255' or "email" => ['required', 'email']
        rule_pattern = re.compile(r"['\"]([^'\"]+)['\"]\s*=>\s*(?:['\"]([^'\"]+)['\"]|\[([^\]]+)\])")
        for match in rule_pattern.finditer(body):
            field = match.group(1)
            raw_rules = match.group(2) or match.group(3) or ""
            
            rules_list = [r.strip().strip("'\"") for r in raw_rules.split("|") if r.strip()]
            if match.group(3):
                rules_list = [r.strip().strip("'\"") for r in match.group(3).split(",") if r.strip()]

            is_required = "required" in rules_list
            p_type = "string"
            p_meta = {"required": is_required}

            for r in rules_list:
                if r in ["integer", "numeric", "int", "digits"]:
                    p_type = "number"
                elif r in ["boolean", "bool"]:
                    p_type = "boolean"
                elif r in ["array"]:
                    p_type = "array"
                elif r in ["email"]:
                    p_meta["format"] = "email"
                elif r.startswith("min:"):
                    try:
                        p_meta["min"] = int(r.split(":")[1])
                    except Exception:
                        pass
                elif r.startswith("max:"):
                    try:
                        p_meta["max"] = int(r.split(":")[1])
                    except Exception:
                        pass

            p_meta["type"] = p_type
            props[field] = p_meta

        return props

    def scan(self) -> List[Dict[str, Any]]:
        if not self._parsed_requests:
            self._parse_form_requests()
            self._parsed_requests = True

        endpoints = []
        route_files = [
            os.path.join(self.project_path, "routes", "api.php"),
            os.path.join(self.project_path, "routes", "web.php")
        ]

        for rf in route_files:
            if not os.path.exists(rf):
                continue
            relpath = os.path.relpath(rf, self.project_path)
            is_api = "api" in relpath
            base_prefix = "/api" if is_api else ""

            try:
                with open(rf, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                content = "".join(lines)
                
                # 1. Route::get/post/put/delete/patch
                route_regex = re.compile(r"Route::(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]*)['\"]\s*,\s*(?:\[\s*([A-Za-z0-9_]+)::class\s*,\s*['\"]([^'\"]+)['\"]\s*\]|['\"]([^'@]+)@([^'\"]+)['\"])", re.IGNORECASE)
                for i, line in enumerate(lines):
                    for m in route_regex.finditer(line):
                        method = m.group(1).upper()
                        path_raw = m.group(2).strip("/")
                        full_path = (base_prefix + "/" + path_raw).rstrip("/")
                        if not full_path.startswith("/"):
                            full_path = "/" + full_path

                        controller = m.group(3) or m.group(5) or "Closure"
                        action = m.group(4) or m.group(6) or "handler"
                        handler_name = f"{controller}@{action}"

                        req_body = self._find_matching_request(controller, action)
                        params = [{"name": p.strip("{}"), "type": "string", "required": True} for p in re.findall(r"\{([a-zA-Z0-9_?]+)\}", full_path)]

                        resp_schema = {
                            "status": 201 if method == "POST" else 200,
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean", "required": True},
                                "data": {"type": "object", "required": True}
                            }
                        }

                        endpoints.append({
                            "method": method,
                            "path": full_path,
                            "handler": handler_name,
                            "summary": f"{method} {full_path} ({handler_name})",
                            "auth": "auth:sanctum" in content or "auth:api" in content,
                            "headers": [{"name": "Content-Type", "type": "string", "required": True, "default": "application/json"}] if method in ["POST", "PUT", "PATCH"] else [],
                            "params": params,
                            "query": [],
                            "request_body": req_body,
                            "response": resp_schema,
                            "mock_request": BaseAdapter.build_mock_from_schema(req_body),
                            "mock_response": BaseAdapter.build_mock_from_schema(resp_schema),
                            "file": relpath,
                            "line": i + 1
                        })

                # 2. Route::apiResource('posts', PostController::class)
                resource_regex = re.compile(r"Route::(?:apiResource|resource)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z0-9_]+)::class\s*\)")
                for i, line in enumerate(lines):
                    for m in resource_regex.finditer(line):
                        res_name = m.group(1).strip("/")
                        controller = m.group(2)
                        res_path = f"{base_prefix}/{res_name}"

                        resource_actions = [
                            ("GET", res_path, "index", 200, None),
                            ("POST", res_path, "store", 201, self._find_matching_request(controller, "store")),
                            ("GET", f"{res_path}/{{id}}", "show", 200, None),
                            ("PUT", f"{res_path}/{{id}}", "update", 200, self._find_matching_request(controller, "update")),
                            ("DELETE", f"{res_path}/{{id}}", "destroy", 200, None),
                        ]

                        for m_verb, r_path, act, status_code, r_body in resource_actions:
                            params = [{"name": "id", "type": "string", "required": True}] if "{id}" in r_path else []
                            resp_schema = {
                                "status": status_code,
                                "type": "object",
                                "properties": {"success": {"type": "boolean", "required": True}, "data": {"type": "object"}}
                            }
                            endpoints.append({
                                "method": m_verb,
                                "path": r_path,
                                "handler": f"{controller}@{act}",
                                "summary": f"{m_verb} {r_path} ({controller}@{act})",
                                "auth": is_api,
                                "headers": [{"name": "Content-Type", "type": "string", "required": True, "default": "application/json"}] if m_verb in ["POST", "PUT", "PATCH"] else [],
                                "params": params,
                                "query": [],
                                "request_body": r_body,
                                "response": resp_schema,
                                "mock_request": BaseAdapter.build_mock_from_schema(r_body),
                                "mock_response": BaseAdapter.build_mock_from_schema(resp_schema),
                                "file": relpath,
                                "line": i + 1
                            })
            except Exception:
                pass

        return endpoints

    def _find_matching_request(self, controller: str, action: str) -> Optional[Dict[str, Any]]:
        # e.g., UserController -> CreateUserRequest or StoreUserRequest
        base_name = controller.replace("Controller", "")
        candidates = [
            f"{action.capitalize()}{base_name}Request",
            f"Store{base_name}Request",
            f"Update{base_name}Request",
            f"{base_name}Request"
        ]
        for c in candidates:
            if c in self.form_requests:
                return {
                    "type": "object",
                    "name": c,
                    "properties": self.form_requests[c]["properties"]
                }
        return None
