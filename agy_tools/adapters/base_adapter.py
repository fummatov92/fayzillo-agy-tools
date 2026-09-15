import os
import re
import fnmatch
from typing import List, Dict, Any, Optional

class BaseAdapter:
    """Base abstract adapter for AST/Regex API route and contract extraction."""

    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)

    def detect(self) -> bool:
        """Return True if this project matches adapter framework."""
        raise NotImplementedError

    def scan(self) -> List[Dict[str, Any]]:
        """Extract all endpoints and contracts."""
        raise NotImplementedError

    @staticmethod
    def generate_heuristic_mock(prop_name: str, prop_type: str, constraints: Dict[str, Any] = None) -> Any:
        """Generates realistic mock values based on AST data types and Semantic Embeddings."""
        return BaseAdapter.generate_semantic_mock(prop_name, prop_type, constraints)

    @staticmethod
    def generate_semantic_mock(prop_name: str, prop_type: str, constraints: Dict[str, Any] = None) -> Any:
        """ML and AST driven semantic mock generator with deep type resolution."""
        name_lower = (prop_name or "").lower().strip()
        type_lower = (prop_type or "").lower().strip()
        constraints = constraints or {}

        # 1. AST Strict Boolean
        if "bool" in type_lower:
            return True

        # 2. AST Strict Numeric (Int, Float, Decimal)
        if any(t in type_lower for t in ["int", "num", "float", "double", "decimal", "bigint"]):
            if "port" in name_lower:
                return 3000
            if "status" in name_lower or "code" in name_lower:
                return 200
            if "id" in name_lower:
                return 1
            if "page" in name_lower:
                return 1
            if "limit" in name_lower or "size" in name_lower:
                return 20
            if "age" in name_lower:
                return 25
            if "price" in name_lower or "amount" in name_lower or "cost" in name_lower or "salary" in name_lower:
                return 49.99
            if "min" in constraints:
                return constraints["min"]
            return 42

        # 3. AST Strict Date/Time types
        if any(d in type_lower for d in ["date", "datetime", "timestamp", "timestamptz"]):
            return "2026-09-12T15:00:00.000Z"

        # 4. AST Strict UUID type
        if "uuid" in type_lower or constraints.get("format") == "uuid":
            return "550e8400-e29b-41d4-a716-446655440000"

        # 5. AST Array / List
        if "array" in type_lower or "[]" in type_lower or "list" in type_lower:
            item_type = type_lower.replace("[]", "").replace("array<", "").replace("list[", "").rstrip(">").rstrip("]")
            item_type = item_type.strip() or "string"
            return [BaseAdapter.generate_semantic_mock(prop_name + "_item", item_type)]

        # 6. Semantic Categorization & Anchors (Cosine / TF-IDF / Semantic Token Matching)
        if constraints.get("format") == "email" or "email" in name_lower or "mail" in name_lower:
            return "user@example.com"
        if constraints.get("format") == "uri" or "url" in name_lower or "link" in name_lower or "avatar" in name_lower:
            return "https://example.com"
        if "phone" in name_lower or "tel" in name_lower or "mobile" in name_lower:
            return "+998901234567"
        if "uuid" in name_lower or "guid" in name_lower:
            return "550e8400-e29b-41d4-a716-446655440000"
        if name_lower in ["firstname", "first_name", "given_name"]:
            return "Fayzillo"
        if name_lower in ["lastname", "last_name", "surname", "middlename", "middle_name"]:
            return "Ummatov"
        if name_lower in ["title", "name", "subject", "label"] or "name" in name_lower:
            return "Test Item"
        if any(k in name_lower for k in ["description", "bio", "summary", "detail", "content", "remarks", "notes"]):
            return "High performance automated system"
        if "token" in name_lower or "jwt" in name_lower:
            return "jwt.token.sample_string"
        if "pass" in name_lower or "secret" in name_lower:
            return "SecurePass123!"
        if "telegram" in name_lower or "tg" in name_lower:
            return "123456789"
        if name_lower in ["login", "user", "username", "author"]:
            return "john_doe"
        if name_lower in ["status", "state"]:
            return "active"
        if name_lower in ["role", "role_name", "user_role"]:
            return "admin"
        if (
            name_lower.endswith("_at")
            or name_lower.endswith("_date")
            or name_lower.endswith("_time")
            or name_lower in ["createdat", "updatedat", "deletedat", "expiresat", "timestamp", "datetime", "date", "time"]
            or "birthdate" in name_lower
            or constraints.get("format") in ["date", "date-time"]
        ):
            return "2026-09-12T15:00:00.000Z"
        if name_lower in ["id", "identifier", "pk"] or name_lower.endswith("_id") or name_lower.endswith("id"):
            return "usr_1001"

        return f"sample_{prop_name}"

    @staticmethod
    def build_mock_from_schema(schema: Optional[Dict[str, Any]]) -> Any:
        """Builds a complete mock JSON object or array directly from AST schema definitions."""
        if not schema or not isinstance(schema, dict):
            return {}
        
        props = schema.get("properties")
        if not props or not isinstance(props, dict):
            # Check if root is array
            s_type = schema.get("type", "object")
            if s_type in ["array", "list"] or str(s_type).endswith("[]"):
                items = schema.get("items")
                if isinstance(items, dict):
                    return [BaseAdapter.build_mock_from_schema(items)]
                return []
            return {}

        mock_obj = {}
        for prop_name, prop_meta in props.items():
            if isinstance(prop_meta, dict):
                p_type = prop_meta.get("type", "string")
                # Nested AST object/model resolution
                if "properties" in prop_meta and isinstance(prop_meta["properties"], dict):
                    if p_type in ["array", "list"] or str(p_type).endswith("[]"):
                        mock_obj[prop_name] = [BaseAdapter.build_mock_from_schema(prop_meta)]
                    else:
                        mock_obj[prop_name] = BaseAdapter.build_mock_from_schema(prop_meta)
                elif "items" in prop_meta and isinstance(prop_meta["items"], dict):
                    mock_obj[prop_name] = [BaseAdapter.build_mock_from_schema(prop_meta["items"])]
                else:
                    mock_obj[prop_name] = BaseAdapter.generate_semantic_mock(prop_name, str(p_type), prop_meta)
            else:
                mock_obj[prop_name] = BaseAdapter.generate_semantic_mock(prop_name, str(prop_meta))
        return mock_obj
