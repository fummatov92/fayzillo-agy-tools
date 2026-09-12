import os
import re
from typing import List, Dict, Any, Optional
from agy_tools.adapters.base_adapter import BaseAdapter

class GoAdapter(BaseAdapter):
    """Zero-token parser for Go (Gin & Fiber) web frameworks and struct tags."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self.structs: Dict[str, Dict[str, Any]] = {}
        self._parsed_structs = False

    def detect(self) -> bool:
        go_mod = os.path.join(self.project_path, "go.mod")
        if os.path.exists(go_mod):
            return True
        for f in os.listdir(self.project_path):
            if f.endswith(".go"):
                return True
        return False

    def _parse_go_structs(self):
        """Scan .go files for struct definitions and tags."""
        struct_pattern = re.compile(r"type\s+([A-Za-z0-9_]+)\s+struct\s*\{([^}]+)\}")
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in [".git", "vendor", "bin", "dist"]]
            for file in files:
                if file.endswith(".go") and not file.endswith("_test.go"):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()

                        for match in struct_pattern.finditer(content):
                            struct_name = match.group(1)
                            body = match.group(2)
                            props = self._parse_struct_fields(body)
                            self.structs[struct_name] = {
                                "name": struct_name,
                                "properties": props,
                                "file": os.path.relpath(filepath, self.project_path)
                            }
                    except Exception:
                        pass

    def _parse_struct_fields(self, body: str) -> Dict[str, Any]:
        props = {}
        for line in body.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("//"):
                continue

            # FieldName Type `json:"..." binding:"..."`
            field_m = re.match(r"([A-Za-z0-9_]+)\s+([*]?[A-Za-z0-9_\[\]]+)(?:\s+`([^`]+)`)?", line)
            if field_m:
                field_name = field_m.group(1)
                go_type = field_m.group(2).lstrip("*")
                tags = field_m.group(3) or ""

                json_name = field_name
                is_required = False
                p_meta = {}

                if tags:
                    json_tag_m = re.search(r'json:"([^"]+)"', tags)
                    if json_tag_m:
                        j_val = json_tag_m.group(1).split(",")[0]
                        if j_val and j_val != "-":
                            json_name = j_val

                    binding_tag_m = re.search(r'binding:"([^"]+)"', tags)
                    validate_tag_m = re.search(r'validate:"([^"]+)"', tags)
                    val_str = (binding_tag_m.group(1) if binding_tag_m else "") + "," + (validate_tag_m.group(1) if validate_tag_m else "")
                    
                    if "required" in val_str:
                        is_required = True
                    if "email" in val_str:
                        p_meta["format"] = "email"
                    if "min=" in val_str:
                        min_v = re.search(r"min=(\d+)", val_str)
                        if min_v:
                            p_meta["min"] = int(min_v.group(1))

                # Map Go type to JSON / TS type
                std_type = "string"
                if go_type in ["int", "int8", "int16", "int32", "int64", "uint", "uint8", "uint16", "uint32", "uint64", "float32", "float64"]:
                    std_type = "number"
                elif go_type == "bool":
                    std_type = "boolean"
                elif go_type.startswith("[]"):
                    std_type = "array"

                p_meta["type"] = std_type
                p_meta["required"] = is_required
                props[json_name] = p_meta

        return props

    def scan(self) -> List[Dict[str, Any]]:
        if not self._parsed_structs:
            self._parse_go_structs()
            self._parsed_structs = True

        endpoints = []
        # Match Gin: r.GET("/api/v1/users", handler) or Fiber: app.Get("/api/v1/users", handler)
        route_pattern = re.compile(r"(?:[a-zA-Z0-9_]+)\.(GET|POST|PUT|DELETE|PATCH|Get|Post|Put|Delete|Patch)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z0-9_.]+)\s*\)")

        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in [".git", "vendor", "bin", "dist"]]
            for file in files:
                if file.endswith(".go") and not file.endswith("_test.go"):
                    filepath = os.path.join(root, file)
                    relpath = os.path.relpath(filepath, self.project_path)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            lines = f.readlines()

                        full_content = "".join(lines)
                        for i, line in enumerate(lines):
                            for m in route_pattern.finditer(line):
                                method = m.group(1).upper()
                                path = m.group(2)
                                handler = m.group(3)

                                # Find bound struct in handler code if present
                                bound_schema = self._find_bound_struct(handler, full_content)
                                
                                params = []
                                for param in re.findall(r":([a-zA-Z0-9_]+)", path):
                                    params.append({"name": param, "type": "string", "required": True})

                                resp_schema = {
                                    "status": 201 if method == "POST" else 200,
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "required": True},
                                        "data": {"type": "object", "required": True}
                                    }
                                }

                                endpoints.append({
                                    "method": method,
                                    "path": path,
                                    "handler": handler,
                                    "summary": f"{method} {path} ({handler})",
                                    "auth": "/auth" in path or "/admin" in path,
                                    "headers": [{"name": "Content-Type", "type": "string", "required": True, "default": "application/json"}] if method in ["POST", "PUT", "PATCH"] else [],
                                    "params": params,
                                    "query": [],
                                    "request_body": bound_schema,
                                    "response": resp_schema,
                                    "mock_request": BaseAdapter.build_mock_from_schema(bound_schema),
                                    "mock_response": BaseAdapter.build_mock_from_schema(resp_schema),
                                    "file": relpath,
                                    "line": i + 1
                                })
                    except Exception:
                        pass

        return endpoints

    def _find_bound_struct(self, handler_name: str, content: str) -> Optional[Dict[str, Any]]:
        clean_handler = handler_name.split(".")[-1]
        handler_body_match = re.search(rf"func\s+(?:\([^)]+\)\s+)?{clean_handler}\s*\([^)]*\)\s*\{{([^}}]+)\}}", content)
        if handler_body_match:
            h_body = handler_body_match.group(1)
            # Find struct instance passed to ShouldBindJSON(&req) or BodyParser(&req)
            var_match = re.search(r"(?:ShouldBindJSON|BodyParser|Bind)\s*\(\s*&([A-Za-z0-9_]+)\s*\)", h_body)
            if var_match:
                var_name = var_match.group(1)
                # Find type of var: var req CreateUserRequest or req := &CreateUserRequest{}
                type_m = re.search(rf"(?:var\s+{var_name}\s+([A-Za-z0-9_]+)|{var_name}\s*:=\s*(?:&)?([A-Za-z0-9_]+)\{{)", h_body)
                if type_m:
                    s_name = type_m.group(1) or type_m.group(2)
                    if s_name in self.structs:
                        return {
                            "type": "object",
                            "name": s_name,
                            "properties": self.structs[s_name]["properties"]
                        }
        return None
