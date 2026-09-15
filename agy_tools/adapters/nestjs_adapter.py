import os
import re
import json
from typing import List, Dict, Any, Optional
from agy_tools.adapters.base_adapter import BaseAdapter

class NestJSAdapter(BaseAdapter):
    """Deep Zero-Token AST/Regex parser for NestJS controllers, DTOs, Services, and Prisma schemas."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self.dtos: Dict[str, Dict[str, Any]] = {}
        self.prisma_models: Dict[str, Dict[str, Any]] = {}
        self.services: Dict[str, Dict[str, Any]] = {}
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
        """Extract full Prisma models, fields, raw types, relations, and indexes."""
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
            # Search anywhere in project for schema.prisma
            for root, dirs, files in os.walk(self.project_path):
                dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build"]]
                if "schema.prisma" in files:
                    schema_file = os.path.join(root, "schema.prisma")
                    break

        if not schema_file:
            return

        try:
            with open(schema_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Find all model blocks: model ModelName { ... }
            model_blocks = re.findall(r"model\s+([A-Za-z0-9_]+)\s*\{([^}]+)\}", content)
            for model_name, block in model_blocks:
                props = {}
                field_details = []
                relations = []
                indexes = []
                uniques = []

                for line in block.strip().split("\n"):
                    line = line.strip()
                    if not line or line.startswith("//"):
                        continue

                    # Capture @@index and @@unique
                    if line.startswith("@@index"):
                        indexes.append(line)
                        continue
                    if line.startswith("@@unique"):
                        uniques.append(line)
                        continue

                    parts = line.split()
                    if len(parts) >= 2:
                        field_name = parts[0]
                        field_type = parts[1]
                        directives = " ".join(parts[2:]) if len(parts) > 2 else ""

                        is_optional = field_type.endswith("?")
                        is_array = field_type.endswith("[]")
                        clean_type = field_type.rstrip("?").rstrip("[]")

                        field_details.append({
                            "name": field_name,
                            "type": field_type,
                            "clean_type": clean_type,
                            "is_optional": is_optional,
                            "is_array": is_array,
                            "directives": directives,
                            "raw_line": f"`{field_name}`: {field_type}{(' ' + directives) if directives else ''}"
                        })

                        if clean_type in ["String", "Int", "Float", "Boolean", "DateTime", "Json", "BigInt", "Decimal", "Bytes"]:
                            ts_type = "string"
                            if clean_type in ["Int", "Float", "Decimal", "BigInt"]:
                                ts_type = "number"
                            elif clean_type == "Boolean":
                                ts_type = "boolean"
                            elif clean_type == "DateTime":
                                ts_type = "string"
                            
                            props[field_name] = {
                                "type": f"{ts_type}[]" if is_array else ts_type,
                                "required": not is_optional,
                                "directives": directives
                            }
                        else:
                            # Relation field or enum
                            rel_match = re.search(r"@relation\(([^)]*)\)", directives)
                            rel_meta = {}
                            if rel_match:
                                rel_args = rel_match.group(1)
                                fields_m = re.search(r"fields:\s*\[([^\]]+)\]", rel_args)
                                refs_m = re.search(r"references:\s*\[([^\]]+)\]", rel_args)
                                on_del_m = re.search(r"onDelete:\s*([A-Za-z0-9_]+)", rel_args)
                                if fields_m: rel_meta["fields"] = fields_m.group(1).strip()
                                if refs_m: rel_meta["references"] = refs_m.group(1).strip()
                                if on_del_m: rel_meta["onDelete"] = on_del_m.group(1).strip()

                            relations.append({
                                "field": field_name,
                                "model": clean_type,
                                "is_array": is_array,
                                "required": not is_optional,
                                "meta": rel_meta
                            })

                self.prisma_models[model_name] = {
                    "name": model_name,
                    "properties": props,
                    "fields": field_details,
                    "relations": relations,
                    "indexes": indexes,
                    "uniques": uniques
                }
        except Exception:
            pass

    def _parse_dto_files(self):
        """Scan and parse all DTO files, capturing properties, decorators, and Swagger examples."""
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

            rel_file = os.path.relpath(filepath, self.project_path)

            # Match class definitions
            class_matches = re.finditer(r"export\s+class\s+([A-Za-z0-9_]+)(?:\s+extends\s+[A-Za-z0-9_]+)?\s*\{", content)
            for m in class_matches:
                class_name = m.group(1)
                start_idx = m.end()
                
                brace_count = 1
                end_idx = start_idx
                while end_idx < len(content) and brace_count > 0:
                    if content[end_idx] == "{":
                        brace_count += 1
                    elif content[end_idx] == "}":
                        brace_count -= 1
                    end_idx += 1

                class_body = content[start_idx:end_idx-1]
                properties, raw_fields = self._parse_dto_class_body(class_body)
                self.dtos[class_name] = {
                    "name": class_name,
                    "properties": properties,
                    "fields": raw_fields,
                    "file": rel_file
                }

            # Match interfaces
            if_matches = re.finditer(r"export\s+interface\s+([A-Za-z0-9_]+)\s*\{([^}]+)\}", content)
            for m in if_matches:
                if_name = m.group(1)
                body = m.group(2)
                props = {}
                raw_fields = []
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
                        raw_fields.append({
                            "name": clean_p_name,
                            "type": p_type,
                            "required": not is_opt,
                            "decorators": []
                        })
                self.dtos[if_name] = {
                    "name": if_name,
                    "properties": props,
                    "fields": raw_fields,
                    "file": rel_file
                }
        except Exception:
            pass

    def _parse_dto_class_body(self, body: str) -> (Dict[str, Any], List[Dict[str, Any]]):
        """Parses property fields and class-validator/swagger decorators in class body."""
        properties = {}
        raw_fields = []
        i = 0
        n = len(body)
        current_decorators = []

        while i < n:
            if body[i].isspace():
                i += 1
                continue

            if body[i:i+2] == "//":
                i = body.find("\n", i)
                if i == -1: break
                continue

            if body[i:i+2] == "/*":
                end_c = body.find("*/", i + 2)
                if end_c == -1: break
                i = end_c + 2
                continue

            if body[i] == "@":
                start_dec = i
                i += 1
                while i < n and (body[i].isalnum() or body[i] in ["_", "$", "."]):
                    i += 1

                temp_i = i
                while temp_i < n and body[temp_i].isspace():
                    temp_i += 1

                if temp_i < n and body[temp_i] == "(":
                    i = temp_i + 1
                    paren_depth = 1
                    in_quote = None
                    escape = False

                    while i < n and paren_depth > 0:
                        ch = body[i]
                        if in_quote:
                            if escape:
                                escape = False
                            elif ch == "\\":
                                escape = True
                            elif ch == in_quote:
                                in_quote = None
                        else:
                            if ch in ["'", '"', "`"]:
                                in_quote = ch
                            elif ch == "(":
                                paren_depth += 1
                            elif ch == ")":
                                paren_depth -= 1
                        i += 1

                dec_text = body[start_dec:i].strip()
                current_decorators.append(dec_text)
                continue

            stmt_start = i
            in_quote = None
            escape = False
            stmt_end = i
            has_colon = False

            while i < n:
                ch = body[i]
                if in_quote:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == in_quote:
                        in_quote = None
                else:
                    if ch in ["'", '"', "`"]:
                        in_quote = ch
                    elif ch == ":":
                        has_colon = True
                    elif ch == ";":
                        stmt_end = i
                        i += 1
                        break
                    elif ch == "\n":
                        stmt_end = i
                        i += 1
                        break
                    elif ch == "@":
                        stmt_end = i
                        break
                    elif ch == "{" and not has_colon:
                        brace_depth = 1
                        i += 1
                        while i < n and brace_depth > 0:
                            if body[i] == "{": brace_depth += 1
                            elif body[i] == "}": brace_depth -= 1
                            i += 1
                        current_decorators = []
                        stmt_start = i
                        break
                i += 1
                stmt_end = i

            stmt_text = body[stmt_start:stmt_end].strip()
            if not stmt_text:
                continue

            field_match = re.match(r"^(?:(?:readonly|public|private|protected)\s+)?([a-zA-Z0-9_$]+)([\?!])?\s*:\s*([^;=]+)", stmt_text)
            if field_match:
                field_name = field_match.group(1)
                opt_or_bang = field_match.group(2)
                raw_type = field_match.group(3).strip()
                is_optional_field = (opt_or_bang == "?")

                prop_meta = {
                    "type": raw_type,
                    "required": not is_optional_field,
                    "decorators": list(current_decorators)
                }

                # Parse swagger example
                for dec in current_decorators:
                    if "@IsOptional()" in dec or "@ApiPropertyOptional" in dec:
                        prop_meta["required"] = False
                    elif "@ApiProperty(" in dec and re.search(r"required\s*:\s*false", dec, re.IGNORECASE):
                        prop_meta["required"] = False

                    # Extract example from ApiProperty({ example: '...' })
                    ex_match = re.search(r"example\s*:\s*([^,\}]+)", dec)
                    if ex_match:
                        raw_ex = ex_match.group(1).strip().strip("'\"`")
                        prop_meta["example"] = raw_ex

                    if "@IsString()" in dec:
                        prop_meta["type"] = "string"
                    elif "@IsNumber(" in dec or "@IsInt(" in dec or "@IsNumber()" in dec or "@IsInt()" in dec:
                        prop_meta["type"] = "number"
                    elif "@IsBoolean()" in dec:
                        prop_meta["type"] = "boolean"
                    elif "@IsArray()" in dec:
                        if not prop_meta["type"].endswith("[]"):
                            prop_meta["type"] = f"{prop_meta['type']}[]" if prop_meta["type"] != "any" else "any[]"
                    elif "@IsEmail(" in dec or "@IsEmail()" in dec:
                        prop_meta["type"] = "string"
                        prop_meta["format"] = "email"
                    elif "@IsUUID(" in dec or "@IsUUID()" in dec:
                        prop_meta["type"] = "string"
                        prop_meta["format"] = "uuid"
                    elif "@IsDate(" in dec or "@IsDate()" in dec or "@IsDateString(" in dec or "@IsDateString()" in dec:
                        prop_meta["type"] = "string"
                        prop_meta["format"] = "date-time"

                    min_m = re.search(r"@Min\((\d+)\)", dec)
                    if min_m: prop_meta["min"] = int(min_m.group(1))
                    max_m = re.search(r"@Max\((\d+)\)", dec)
                    if max_m: prop_meta["max"] = int(max_m.group(1))
                    len_m = re.search(r"@Length\((\d+)(?:,\s*(\d+))?\)", dec)
                    if len_m:
                        prop_meta["minLength"] = int(len_m.group(1))
                        if len_m.group(2): prop_meta["maxLength"] = int(len_m.group(2))
                    min_len_m = re.search(r"@MinLength\((\d+)\)", dec)
                    if min_len_m: prop_meta["minLength"] = int(min_len_m.group(1))
                    max_len_m = re.search(r"@MaxLength\((\d+)\)", dec)
                    if max_len_m: prop_meta["maxLength"] = int(max_len_m.group(1))

                properties[field_name] = prop_meta
                raw_fields.append({
                    "name": field_name,
                    "type": prop_meta["type"],
                    "required": prop_meta["required"],
                    "decorators": list(current_decorators),
                    "example": prop_meta.get("example")
                })
                current_decorators = []
            else:
                current_decorators = []

        return properties, raw_fields

    def _scan_services(self):
        """Scan all NestJS service files and parse methods, exceptions, and Prisma operations."""
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build", ".next", ".angular"]]
            for file in files:
                if file.endswith((".service.ts", ".service.js")):
                    filepath = os.path.join(root, file)
                    rel_file = os.path.relpath(filepath, self.project_path)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()

                        class_match = re.search(r"export\s+class\s+([A-Za-z0-9_]+)", content)
                        if not class_match:
                            continue
                        svc_class = class_match.group(1)

                        # Extract methods: async methodName(...) { ... }
                        methods = {}
                        method_matches = re.finditer(r"(?:async\s+)?([a-zA-Z0-9_]+)\s*\(([^)]*)\)\s*(?::\s*([^{]+))?\{", content)
                        for mm in method_matches:
                            m_name = mm.group(1)
                            if m_name in ["constructor", "if", "for", "while", "switch", "catch"]:
                                continue

                            start_b = mm.end() - 1
                            brace_count = 1
                            curr = start_b + 1
                            while curr < len(content) and brace_count > 0:
                                if content[curr] == "{":
                                    brace_count += 1
                                elif content[curr] == "}":
                                    brace_count -= 1
                                curr += 1
                            
                            m_body = content[start_b:curr]

                            # Extract exceptions: throw new UnauthorizedException('...')
                            exceptions = []
                            exc_matches = re.finditer(r"throw\s+new\s+([A-Za-z0-9_]+Exception)\s*\(([^)]*)\)", m_body)
                            for em in exc_matches:
                                exc_type = em.group(1)
                                exc_arg = em.group(2).strip()
                                # Clean message string
                                msg_match = re.search(r"['\"`]([^'\"`]+)['\"`]", exc_arg)
                                msg = msg_match.group(1) if msg_match else exc_arg
                                exceptions.append({
                                    "type": exc_type,
                                    "message": msg
                                })

                            # Extract Prisma operations: this.prisma.user.findFirst / prisma.tableName.create
                            prisma_ops = []
                            prisma_matches = re.finditer(r"(?:this\.)?prisma\.([a-zA-Z0-9_]+)\.(findFirst|findUnique|findMany|create|createMany|update|updateMany|upsert|delete|deleteMany|count)\b", m_body)
                            for pm in prisma_matches:
                                model_ref = pm.group(1)
                                op_type = pm.group(2)
                                prisma_ops.append({
                                    "model": model_ref,
                                    "operation": op_type
                                })

                            # Infer summary
                            summary = f"{m_name} mantiqiy biznes operatsiyasini bajaradi."
                            if "find" in m_name.lower() or "get" in m_name.lower():
                                summary = f"Ma'lumotlar bazasidan tegishli yozuvlarni qidiradi va filtrlaydi."
                            elif "create" in m_name.lower() or "add" in m_name.lower():
                                summary = f"Yangi yozuvni tekshiradi va ma'lumotlar bazasiga saqlaydi."
                            elif "update" in m_name.lower() or "edit" in m_name.lower():
                                summary = f"Mavjud yozuvni tekshiradi va yangilaydi."
                            elif "delete" in m_name.lower() or "remove" in m_name.lower():
                                summary = f"Ko'rsatilgan yozuvni ma'lumotlar bazasidan o'chiradi."
                            elif "login" in m_name.lower() or "auth" in m_name.lower():
                                summary = f"Foydalanuvchi hisob ma'lumotlarini tekshiradi, JWT access/refresh token yaratadi va tizimga kirishni tasdiqlaydi."

                            methods[m_name] = {
                                "name": m_name,
                                "exceptions": exceptions,
                                "prisma_ops": prisma_ops,
                                "summary": summary,
                                "file": rel_file,
                                "class": svc_class
                            }

                        self.services[svc_class] = {
                            "class": svc_class,
                            "file": rel_file,
                            "methods": methods
                        }
                    except Exception:
                        pass

    def _find_global_prefix(self) -> str:
        candidate_files = [
            "src/main.ts", "src/main.js", "main.ts", "main.js",
            "src/bootstrap.ts", "src/bootstrap.js", "src/index.ts", "src/index.js",
            "src/app.ts", "src/app.js", "src/server.ts", "src/server.js"
        ]
        found_files = []
        for rel in candidate_files:
            p = os.path.join(self.project_path, rel)
            if os.path.exists(p):
                found_files.append(p)
                
        if not found_files:
            for root, dirs, files in os.walk(self.project_path):
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

                    # 3. Variable reference (e.g., app.setGlobalPrefix(API_PREFIX))
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

    def scan(self) -> List[Dict[str, Any]]:
        """Extract all NestJS routes, parameters, DTOs, service traces, exceptions, and DB models."""
        if not self._parsed:
            self._parse_prisma_schema()
            self._parse_dto_files()
            self._scan_services()
            self._parsed = True

        global_prefix = self._find_global_prefix()
        endpoints = []
        controller_regex = re.compile(r"@Controller\((?:['\"]([^'\"]*)['\"])?\)")
        method_regex = re.compile(r"@(Get|Post|Put|Delete|Patch|Options|Head)\((?:['\"]([^'\"]*)['\"])?\)")
        func_regex = re.compile(r"(?:async\s+)?([a-zA-Z0-9_]+)\s*\(")
        auth_regex = re.compile(r"@(UseGuards|Auth|ApiBearerAuth|Roles|JwtAuthGuard)")
        public_regex = re.compile(r"@Public\(\)")
        roles_regex = re.compile(r"@Roles\(([^)]*)\)")
        RESERVED_WORDS = {"constructor", "if", "for", "while", "switch", "return", "catch", "try"}

        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build", ".next", ".angular"]]
            for file in files:
                if file.endswith((".controller.ts", ".controller.js")):
                    filepath = os.path.join(root, file)
                    relpath = os.path.relpath(filepath, self.project_path)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()

                        # Extract controller class name
                        ctrl_class_match = re.search(r"export\s+class\s+([A-Za-z0-9_]+)", content)
                        ctrl_class_name = ctrl_class_match.group(1) if ctrl_class_match else "AppController"

                        # Extract constructor dependency injection (mapping this.xxxService -> ServiceClass)
                        injected_services = {}
                        ctor_match = re.search(r"constructor\s*\(([^)]*)\)", content)
                        if ctor_match:
                            ctor_params = ctor_match.group(1)
                            for param_match in re.finditer(r"(?:private|protected|public)?\s*(?:readonly)?\s*([a-zA-Z0-9_$]+)\s*:\s*([a-zA-Z0-9_$]+)", ctor_params):
                                var_name = param_match.group(1)
                                type_name = param_match.group(2)
                                injected_services[var_name] = type_name

                        lines = content.split("\n")
                        base_route = ""
                        controller_auth = False
                        controller_public = False
                        controller_roles = []

                        for i, line in enumerate(lines):
                            ctrl_match = controller_regex.search(line)
                            if ctrl_match:
                                base_route = ctrl_match.group(1) or ""
                                for prev in lines[max(0, i-8):i]:
                                    if auth_regex.search(prev):
                                        controller_auth = True
                                    if public_regex.search(prev):
                                        controller_public = True
                                    rm = roles_regex.search(prev)
                                    if rm:
                                        controller_roles = [r.strip().strip("'\"`") for r in rm.group(1).split(",") if r.strip()]

                            m_match = method_regex.search(line)
                            if m_match:
                                http_verb = m_match.group(1).upper()
                                sub_path = m_match.group(2) or ""

                                # Check route-level auth & roles in preceding 8 lines
                                route_auth = controller_auth
                                route_public = controller_public
                                route_roles = list(controller_roles)
                                applied_guards = []
                                swagger_summary = ""

                                for prev in lines[max(0, i-8):i]:
                                    if auth_regex.search(prev):
                                        route_auth = True
                                        applied_guards.append(prev.strip())
                                    if public_regex.search(prev):
                                        route_public = True
                                        applied_guards.append("@Public()")
                                    rm = roles_regex.search(prev)
                                    if rm:
                                        route_roles = [r.strip().strip("'\"`") for r in rm.group(1).split(",") if r.strip()]
                                        applied_guards.append(prev.strip())
                                    op_m = re.search(r"@ApiOperation\(\s*\{[^}]*summary\s*:\s*['\"`]([^'\"`]+)['\"`]", prev)
                                    if op_m:
                                        swagger_summary = op_m.group(1)

                                # Find method name
                                func_name = "handler"
                                func_line_idx = i + 1
                                for next_idx in range(i + 1, min(i + 15, len(lines))):
                                    trimmed = lines[next_idx].strip()
                                    if trimmed.startswith("@") or trimmed.startswith("//") or not trimmed:
                                        if auth_regex.search(trimmed): route_auth = True
                                        if public_regex.search(trimmed): route_public = True
                                        rm = roles_regex.search(trimmed)
                                        if rm: route_roles = [r.strip().strip("'\"`") for r in rm.group(1).split(",") if r.strip()]
                                        continue
                                    f_match = func_regex.search(trimmed)
                                    if f_match and f_match.group(1) not in RESERVED_WORDS:
                                        func_name = f_match.group(1)
                                        func_line_idx = next_idx
                                        break

                                # Extract method body block
                                body_start = func_line_idx
                                method_body = ""
                                for b_idx in range(func_line_idx, min(func_line_idx + 60, len(lines))):
                                    method_body += lines[b_idx] + "\n"
                                    if "}" in lines[b_idx] and b_idx > func_line_idx + 1:
                                        # check if brace count balance
                                        if method_body.count("{") <= method_body.count("}"):
                                            break

                                # Trace Service and Method
                                called_service = None
                                called_svc_method = None
                                svc_trace = None

                                # Look for this.<serviceVar>.<methodName>(...)
                                for var_name, svc_type in injected_services.items():
                                    call_m = re.search(r"this\." + re.escape(var_name) + r"\.([a-zA-Z0-9_]+)\s*\(", method_body)
                                    if call_m:
                                        called_service = svc_type
                                        called_svc_method = call_m.group(1)
                                        break

                                if not called_service:
                                    # Fallback: search any this.xxxService.yyy(...)
                                    call_m = re.search(r"this\.([a-zA-Z0-9_]+Service)\.([a-zA-Z0-9_]+)\s*\(", method_body)
                                    if call_m:
                                        svc_var = call_m.group(1)
                                        called_service = svc_var[0].upper() + svc_var[1:]
                                        called_svc_method = call_m.group(2)

                                # If service is found, look up details
                                error_cases = []
                                db_models_accessed = []
                                service_summary = f"{ctrl_class_name}.{func_name} orqali so'rov qabul qilinadi va qayta ishlanadi."
                                service_file_path = ""

                                if called_service and called_service in self.services:
                                    svc_data = self.services[called_service]
                                    service_file_path = svc_data.get("file", "")
                                    if called_svc_method and called_svc_method in svc_data.get("methods", {}):
                                        m_info = svc_data["methods"][called_svc_method]
                                        service_summary = m_info.get("summary", service_summary)
                                        for exc in m_info.get("exceptions", []):
                                            error_cases.append({
                                                "exception": exc["type"],
                                                "message": exc["message"],
                                                "reason": f"Shart bajarilmaganda ({exc['message']})"
                                            })
                                        for pop in m_info.get("prisma_ops", []):
                                            m_name_cap = pop["model"][0].upper() + pop["model"][1:]
                                            db_models_accessed.append({
                                                "model": m_name_cap,
                                                "operation": pop["operation"]
                                            })

                                # Also check direct controller exceptions
                                for direct_exc in re.finditer(r"throw\s+new\s+([A-Za-z0-9_]+Exception)\s*\(([^)]*)\)", method_body):
                                    e_type = direct_exc.group(1)
                                    e_arg = direct_exc.group(2).strip()
                                    msg_m = re.search(r"['\"`]([^'\"`]+)['\"`]", e_arg)
                                    msg_str = msg_m.group(1) if msg_m else e_arg
                                    error_cases.append({
                                        "exception": e_type,
                                        "message": msg_str,
                                        "reason": f"Controller darajasidagi xatolik ({msg_str})"
                                    })

                                # Extract multi-line signature params
                                signature_text = ""
                                for sig_idx in range(func_line_idx, min(func_line_idx + 25, len(lines))):
                                    signature_text += lines[sig_idx] + " "
                                    if ")" in lines[sig_idx] and "{" in lines[sig_idx]:
                                        break

                                req_body_schema, params, query = self._parse_signature_params(signature_text)

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
                                
                                # Response contract
                                response_schema = self._infer_response_schema(http_verb, func_name, base_route)

                                # Model matching from route / controller if not captured from service
                                if not db_models_accessed:
                                    raw_seg = base_route.strip("/").split("/")[-1] if base_route.strip("/") else "Item"
                                    candidate_m = "".join(p.capitalize() for p in re.split(r"[-_\s]+", raw_seg) if p).rstrip("s")
                                    if candidate_m in self.prisma_models:
                                        db_models_accessed.append({
                                            "model": candidate_m,
                                            "operation": "o'qish/yozish"
                                        })

                                # Enrich DB model info with full Prisma schema definitions
                                db_structures = []
                                for dba in db_models_accessed:
                                    mname = dba["model"]
                                    if mname in self.prisma_models:
                                        pmodel = self.prisma_models[mname]
                                        db_structures.append({
                                            "model": mname,
                                            "operation": dba["operation"],
                                            "fields": pmodel.get("fields", []),
                                            "relations": pmodel.get("relations", []),
                                            "indexes": pmodel.get("indexes", []),
                                            "uniques": pmodel.get("uniques", [])
                                        })

                                endpoint_item = {
                                    "method": http_verb,
                                    "path": full_path,
                                    "handler": func_name,
                                    "controller_class": ctrl_class_name,
                                    "summary": swagger_summary or f"{http_verb} {full_path} handler ({func_name})",
                                    "auth": route_auth and not route_public,
                                    "is_public": route_public,
                                    "roles": route_roles,
                                    "applied_guards": applied_guards,
                                    "headers": [{"name": "Content-Type", "type": "string", "required": True, "default": "application/json"}] if http_verb in ["POST", "PUT", "PATCH"] else [],
                                    "params": params,
                                    "query": query,
                                    "request_body": req_body_schema,
                                    "response": response_schema,
                                    "mock_request": BaseAdapter.build_mock_from_schema(req_body_schema),
                                    "mock_response": BaseAdapter.build_mock_from_schema(response_schema),
                                    "service_info": {
                                        "class": called_service or f"{ctrl_class_name.replace('Controller', 'Service')}",
                                        "method": called_svc_method or func_name,
                                        "file": service_file_path or relpath.replace(".controller.", ".service."),
                                        "description": service_summary
                                    },
                                    "error_cases": error_cases,
                                    "db_structures": db_structures,
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
                    "properties": inline_props,
                    "file": ""
                }
            elif dto_type in self.dtos:
                dto_info = self.dtos[dto_type]
                req_body = {
                    "type": "object",
                    "name": dto_type,
                    "properties": dto_info.get("properties", {}),
                    "fields": dto_info.get("fields", []),
                    "file": dto_info.get("file", "")
                }
            else:
                req_body = {
                    "type": "object",
                    "name": dto_type,
                    "properties": {"data": {"type": dto_type, "required": True}},
                    "file": ""
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
        """Infers realistic response schema using AST Prisma models or DTO schemas."""
        raw_segment = base_route.strip("/").split("/")[-1] if base_route.strip("/") else "Item"
        parts = re.split(r"[-_\s]+", raw_segment)
        clean_name = "".join(p.capitalize() for p in parts if p)
        if clean_name.endswith("s") and len(clean_name) > 3:
            model_name = clean_name[:-1]
        else:
            model_name = clean_name or "Item"

        # Case-insensitive / normalized lookup in AST Prisma models
        matched_model = None
        for pm in self.prisma_models:
            if pm.lower() == model_name.lower() or pm.lower() == clean_name.lower():
                matched_model = pm
                break

        if matched_model and matched_model in self.prisma_models:
            model_name = matched_model
            model_props = self.prisma_models[matched_model]["properties"]
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
                        "data": {
                            "type": "array",
                            "model": model_name,
                            "required": True,
                            "items": {
                                "type": "object",
                                "model": model_name,
                                "properties": model_props
                            },
                            "properties": model_props
                        },
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
                    "data": {
                        "type": "object",
                        "model": model_name,
                        "required": True,
                        "properties": model_props
                    }
                }
            }
        elif method == "POST":
            return {
                "status": 201,
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "required": True},
                    "data": {
                        "type": "object",
                        "model": model_name,
                        "required": True,
                        "properties": model_props
                    },
                    "message": {"type": "string", "required": False}
                }
            }
        elif method in ["PUT", "PATCH"]:
            return {
                "status": 200,
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "required": True},
                    "data": {
                        "type": "object",
                        "model": model_name,
                        "required": True,
                        "properties": model_props
                    },
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
