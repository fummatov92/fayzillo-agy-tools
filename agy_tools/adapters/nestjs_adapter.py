import os
import re
import json
from typing import List, Dict, Any, Optional
from agy_tools.adapters.base_adapter import BaseAdapter

class NestJSAdapter(BaseAdapter):
    """Zero-token AST/Regex parser for NestJS controllers, DTOs, and Prisma schemas."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self.dtos: Dict[str, Dict[str, Any]] = {}
        self.prisma_models: Dict[str, Dict[str, Any]] = {}
        self._parsed = False

    def detect(self) -> bool:
        pkg_json = os.path.join(self.project_path, "package.json")
        if os.path.exists(pkg_json):
            try:
                with open(pkg_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    return "@nestjs/core" in deps or "@nestjs/common" in deps
            except Exception:
                pass
        return False

    def _parse_prisma_schema(self):
        """Extract Prisma models and fields (max_depth=1)."""
        prisma_paths = [
            os.path.join(self.project_path, "prisma", "schema.prisma"),
            os.path.join(self.project_path, "schema.prisma")
        ]
        
        schema_file = None
        for p in prisma_paths:
            if os.path.exists(p):
                schema_file = p
                break
                
        if not schema_file:
            return

        try:
            with open(schema_file, "r", encoding="utf-8") as f:
                content = f.read()

            model_blocks = re.findall(r"model\s+([A-Za-z0-9_]+)\s*\{([^}]+)\}", content)
            for model_name, block in model_blocks:
                props = {}
                relations = []
                for line in block.strip().split("\n"):
                    line = line.strip()
                    if not line or line.startswith("//") or line.startswith("@@"):
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        field_name = parts[0]
                        field_type = parts[1]
                        is_optional = field_type.endswith("?")
                        is_array = field_type.endswith("[]")
                        clean_type = field_type.rstrip("?").rstrip("[]")

                        if clean_type in ["String", "Int", "Float", "Boolean", "DateTime", "Json", "BigInt", "Decimal"]:
                            ts_type = "string"
                            if clean_type in ["Int", "Float", "Decimal", "BigInt"]:
                                ts_type = "number"
                            elif clean_type == "Boolean":
                                ts_type = "boolean"
                            elif clean_type == "DateTime":
                                ts_type = "string"
                            
                            props[field_name] = {
                                "type": f"{ts_type}[]" if is_array else ts_type,
                                "required": not is_optional
                            }
                        else:
                            # Relation field
                            relations.append({
                                "field": field_name,
                                "model": clean_type,
                                "is_array": is_array,
                                "required": not is_optional
                            })

                self.prisma_models[model_name] = {
                    "name": model_name,
                    "properties": props,
                    "relations": relations
                }
        except Exception:
            pass

    def _parse_dto_files(self):
        """Scan and parse all DTO files and class-validator decorators."""
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build", ".next", ".angular"]]
            for file in files:
                if file.endswith((".dto.ts", ".dto.js", ".entity.ts", ".interface.ts")):
                    filepath = os.path.join(root, file)
                    self._parse_single_dto_file(filepath)

    def _parse_single_dto_file(self, filepath: str):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # Match class definitions: class CreateUserDto { ... }
            class_matches = re.finditer(r"export\s+class\s+([A-Za-z0-9_]+)(?:\s+extends\s+[A-Za-z0-9_]+)?\s*\{", content)
            for m in class_matches:
                class_name = m.group(1)
                start_idx = m.end()
                
                # Find matching closing brace
                brace_count = 1
                end_idx = start_idx
                while end_idx < len(content) and brace_count > 0:
                    if content[end_idx] == "{":
                        brace_count += 1
                    elif content[end_idx] == "}":
                        brace_count -= 1
                    end_idx += 1

                class_body = content[start_idx:end_idx-1]
                properties = self._parse_dto_class_body(class_body)
                self.dtos[class_name] = {
                    "name": class_name,
                    "properties": properties,
                    "file": os.path.relpath(filepath, self.project_path)
                }

            # Match interface definitions: export interface UserResponse { ... }
            if_matches = re.finditer(r"export\s+interface\s+([A-Za-z0-9_]+)\s*\{([^}]+)\}", content)
            for m in if_matches:
                if_name = m.group(1)
                body = m.group(2)
                props = {}
                for line in body.strip().split("\n"):
                    line = line.strip().rstrip(";")
                    if not line or line.startswith("//"):
                        continue
                    if ":" in line:
                        p_parts = line.split(":", 1)
                        p_name = p_parts[0].strip()
                        p_type = p_parts[1].strip()
                        is_opt = p_name.endswith("?")
                        clean_p_name = p_name.rstrip("?")
                        props[clean_p_name] = {
                            "type": p_type,
                            "required": not is_opt
                        }
                self.dtos[if_name] = {
                    "name": if_name,
                    "properties": props,
                    "file": os.path.relpath(filepath, self.project_path)
                }
        except Exception:
            pass

    def _parse_dto_class_body(self, body: str) -> Dict[str, Any]:
        """Parses property fields and class-validator decorators in class body."""
        properties = {}
        lines = body.split("\n")
        
        current_decorators = []
        for line in lines:
            trimmed = line.strip()
            if not trimmed or trimmed.startswith("//"):
                continue

            if trimmed.startswith("@"):
                current_decorators.append(trimmed)
                continue

            # Field definition: name?: string; or readonly name: string;
            field_match = re.match(r"(?:readonly\s+|public\s+|private\s+)?([a-zA-Z0-9_]+)(\?)?\s*:\s*([^;=]+)", trimmed)
            if field_match:
                field_name = field_match.group(1)
                is_optional_field = bool(field_match.group(2))
                raw_type = field_match.group(3).strip()

                prop_meta = {
                    "type": raw_type,
                    "required": not is_optional_field
                }

                # Evaluate class-validator decorators
                for dec in current_decorators:
                    if "@IsOptional()" in dec:
                        prop_meta["required"] = False
                    if "@IsString()" in dec:
                        prop_meta["type"] = "string"
                    elif "@IsNumber(" in dec or "@IsInt()" in dec:
                        prop_meta["type"] = "number"
                    elif "@IsBoolean()" in dec:
                        prop_meta["type"] = "boolean"
                    elif "@IsArray()" in dec:
                        if not prop_meta["type"].endswith("[]"):
                            prop_meta["type"] = f"{prop_meta['type']}[]" if prop_meta["type"] != "any" else "any[]"
                    elif "@IsEmail(" in dec:
                        prop_meta["type"] = "string"
                        prop_meta["format"] = "email"
                    elif "@IsUUID(" in dec:
                        prop_meta["type"] = "string"
                        prop_meta["format"] = "uuid"
                    
                    min_m = re.search(r"@Min\((\d+)\)", dec)
                    if min_m:
                        prop_meta["min"] = int(min_m.group(1))
                    max_m = re.search(r"@Max\((\d+)\)", dec)
                    if max_m:
                        prop_meta["max"] = int(max_m.group(1))
                    len_m = re.search(r"@Length\((\d+)(?:,\s*(\d+))?\)", dec)
                    if len_m:
                        prop_meta["minLength"] = int(len_m.group(1))
                        if len_m.group(2):
                            prop_meta["maxLength"] = int(len_m.group(2))

                properties[field_name] = prop_meta
                current_decorators = []
            else:
                # If non-field and non-decorator line, reset decorators
                if not trimmed.startswith("@"):
                    current_decorators = []

        return properties

    def scan(self) -> List[Dict[str, Any]]:
        """Extract all NestJS routes, parameters, DTOs, and response contracts."""
        if not self._parsed:
            self._parse_prisma_schema()
            self._parse_dto_files()
            self._parsed = True

        endpoints = []
        controller_regex = re.compile(r"@Controller\((?:['\"]([^'\"]*)['\"])?\)")
        method_regex = re.compile(r"@(Get|Post|Put|Delete|Patch|Options|Head)\((?:['\"]([^'\"]*)['\"])?\)")
        func_regex = re.compile(r"(?:async\s+)?([a-zA-Z0-9_]+)\s*\(")
        auth_regex = re.compile(r"@(UseGuards|Auth|ApiBearerAuth|Roles|JwtAuthGuard)")
        RESERVED_WORDS = {"constructor", "if", "for", "while", "switch", "return", "catch", "try"}

        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build", ".next", ".angular"]]
            for file in files:
                if file.endswith((".controller.ts", ".controller.js")):
                    filepath = os.path.join(root, file)
                    relpath = os.path.relpath(filepath, self.project_path)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            lines = f.readlines()

                        base_route = ""
                        controller_auth = False

                        for i, line in enumerate(lines):
                            ctrl_match = controller_regex.search(line)
                            if ctrl_match:
                                base_route = ctrl_match.group(1) or ""
                                # Check if controller-level auth guard exists in preceding 5 lines
                                for prev in lines[max(0, i-5):i]:
                                    if auth_regex.search(prev):
                                        controller_auth = True

                            m_match = method_regex.search(line)
                            if m_match:
                                http_verb = m_match.group(1).upper()
                                sub_path = m_match.group(2) or ""

                                # Check route-level auth in preceding lines
                                route_auth = controller_auth
                                for prev in lines[max(0, i-5):i]:
                                    if auth_regex.search(prev):
                                        route_auth = True

                                # Find handler name and capture method signature block
                                func_name = "handler"
                                func_line_idx = i + 1
                                for next_idx in range(i + 1, min(i + 15, len(lines))):
                                    trimmed = lines[next_idx].strip()
                                    if trimmed.startswith("@") or trimmed.startswith("//") or not trimmed:
                                        if auth_regex.search(trimmed):
                                            route_auth = True
                                        continue
                                    f_match = func_regex.search(trimmed)
                                    if f_match and f_match.group(1) not in RESERVED_WORDS:
                                        func_name = f_match.group(1)
                                        func_line_idx = next_idx
                                        break

                                # Extract multi-line signature params starting from func_line_idx
                                signature_text = ""
                                for sig_idx in range(func_line_idx, min(func_line_idx + 25, len(lines))):
                                    signature_text += lines[sig_idx] + " "
                                    if ")" in lines[sig_idx] and "{" in lines[sig_idx]:
                                        break

                                req_body_schema, params, query = self._parse_signature_params(signature_text)

                                full_path = "/" + "/".join(filter(None, [base_route.strip("/"), sub_path.strip("/")]))
                                
                                # Response contract
                                response_schema = self._infer_response_schema(http_verb, func_name, base_route)

                                endpoint_item = {
                                    "method": http_verb,
                                    "path": full_path,
                                    "handler": func_name,
                                    "summary": f"{http_verb} {full_path} handler ({func_name})",
                                    "auth": route_auth,
                                    "headers": [{"name": "Content-Type", "type": "string", "required": True, "default": "application/json"}] if http_verb in ["POST", "PUT", "PATCH"] else [],
                                    "params": params,
                                    "query": query,
                                    "request_body": req_body_schema,
                                    "response": response_schema,
                                    "mock_request": BaseAdapter.build_mock_from_schema(req_body_schema),
                                    "mock_response": BaseAdapter.build_mock_from_schema(response_schema),
                                    "file": relpath,
                                    "line": i + 1
                                }
                                endpoints.append(endpoint_item)
                    except Exception:
                        pass
        return endpoints

    def _parse_signature_params(self, sig: str):
        """Extract @Body, @Param, @Query from method signature."""
        req_body = None
        params = []
        query = []

        # @Body() paramName: DtoType or inline object
        body_match = re.search(r"@Body\([^)]*\)\s*(?:readonly\s+)?([a-zA-Z0-9_]+)?\s*:\s*([^,){]+|\{[^}]+\})", sig)
        if body_match:
            dto_type = body_match.group(2).strip()
            if dto_type.startswith("{") and dto_type.endswith("}"):
                # Inline object
                inline_props = {}
                for p_line in dto_type.strip("{}").split(";"):
                    p_line = p_line.strip()
                    if ":" in p_line:
                        pn, pt = p_line.split(":", 1)
                        is_opt = pn.strip().endswith("?")
                        inline_props[pn.strip().rstrip("?")] = {
                            "type": pt.strip(),
                            "required": not is_opt
                        }
                req_body = {
                    "type": "object",
                    "name": "InlineBodyDto",
                    "properties": inline_props
                }
            elif dto_type in self.dtos:
                req_body = {
                    "type": "object",
                    "name": dto_type,
                    "properties": self.dtos[dto_type].get("properties", {})
                }
            else:
                req_body = {
                    "type": "object",
                    "name": dto_type,
                    "properties": {"data": {"type": dto_type, "required": True}}
                }

        # @Param('name') name: type
        param_matches = re.finditer(r"@Param\((?:['\"]([^'\"]*)['\"])?\)\s*([a-zA-Z0-9_]+)?\s*(?::\s*([^,)]+))?", sig)
        for pm in param_matches:
            p_name = pm.group(1) or pm.group(2) or "id"
            p_type = (pm.group(3) or "string").strip()
            params.append({
                "name": p_name,
                "type": p_type,
                "required": True
            })

        # @Query('name') or @Query() query: Dto
        query_matches = re.finditer(r"@Query\((?:['\"]([^'\"]*)['\"])?\)\s*([a-zA-Z0-9_]+)?\s*(?::\s*([^,)]+))?", sig)
        for qm in query_matches:
            q_name = qm.group(1) or qm.group(2) or "query"
            q_type = (qm.group(3) or "string").strip()
            if q_type in self.dtos:
                for prop_k, prop_v in self.dtos[q_type].get("properties", {}).items():
                    query.append({
                        "name": prop_k,
                        "type": prop_v.get("type", "string"),
                        "required": prop_v.get("required", False)
                    })
            else:
                query.append({
                    "name": q_name,
                    "type": q_type,
                    "required": False
                })

        return req_body, params, query

    def _infer_response_schema(self, method: str, handler: str, base_route: str) -> Dict[str, Any]:
        """Infers realistic response schema using heuristics or Prisma models."""
        raw_segment = base_route.strip("/").split("/")[-1] if base_route.strip("/") else "Item"
        # Convert kebab/snake to PascalCase
        parts = re.split(r"[-_\s]+", raw_segment)
        clean_name = "".join(p.capitalize() for p in parts if p)
        # Singularize simple plural (Users -> User, Items -> Item)
        if clean_name.endswith("s") and len(clean_name) > 3:
            model_name = clean_name[:-1]
        else:
            model_name = clean_name or "Item"

        # Check if prisma model exists
        if model_name in self.prisma_models:
            model_props = self.prisma_models[model_name]["properties"]
        else:
            model_props = {
                "id": {"type": "string", "required": True},
                "createdAt": {"type": "string", "required": True},
                "updatedAt": {"type": "string", "required": True}
            }

        if method == "GET":
            if any(k in handler.lower() for k in ["list", "all", "findmany", "getall"]):
                return {
                    "status": 200,
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "required": True},
                        "data": {"type": f"{model_name}[]", "required": True},
                        "total": {"type": "number", "required": True},
                        "page": {"type": "number", "required": False},
                        "limit": {"type": "number", "required": False}
                    }
                }
            return {
                "status": 200,
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "required": True},
                    "data": {"type": model_name, "required": True, **model_props}
                }
            }
        elif method == "POST":
            return {
                "status": 201,
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "required": True},
                    "data": {"type": model_name, "required": True, **model_props},
                    "message": {"type": "string", "required": False}
                }
            }
        elif method in ["PUT", "PATCH"]:
            return {
                "status": 200,
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "required": True},
                    "data": {"type": model_name, "required": True, **model_props},
                    "message": {"type": "string", "required": False}
                }
            }
        elif method == "DELETE":
            return {
                "status": 200,
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "required": True},
                    "message": {"type": "string", "required": True}
                }
            }
        return {
            "status": 200,
            "type": "object",
            "properties": {"success": {"type": "boolean", "required": True}}
        }
