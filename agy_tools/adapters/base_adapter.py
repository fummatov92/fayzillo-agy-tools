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
        """Generates realistic mock values based on field name and type heuristics."""
        name_lower = prop_name.lower()
        type_lower = prop_type.lower()
        constraints = constraints or {}

        # 1. Boolean
        if "bool" in type_lower:
            return True

        # 2. Number / Integer / Float
        if any(t in type_lower for t in ["int", "num", "float", "double"]):
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
            if "price" in name_lower or "amount" in name_lower or "cost" in name_lower:
                return 49.99
            if "min" in constraints:
                return constraints["min"]
            return 42

        # 3. Array
        if "array" in type_lower or "[]" in type_lower or "list" in type_lower:
            item_type = type_lower.replace("[]", "").replace("array<", "").replace("list[", "").rstrip(">").rstrip("]")
            item_type = item_type.strip() or "string"
            return [BaseAdapter.generate_heuristic_mock(prop_name + "_item", item_type)]

        # 4. Strings & Special formats
        if "email" in name_lower or constraints.get("format") == "email":
            return "user@example.com"
        if "phone" in name_lower or "tel" in name_lower:
            return "+998901234567"
        if "url" in name_lower or "link" in name_lower:
            return "https://example.com"
        if "uuid" in name_lower or "guid" in name_lower:
            return "550e8400-e29b-41d4-a716-446655440000"
        if "first" in name_lower and "name" in name_lower:
            return "Fayzillo"
        if "last" in name_lower and "name" in name_lower:
            return "Ummatov"
        if "name" in name_lower or "title" in name_lower:
            return "Test Item"
        if "description" in name_lower or "bio" in name_lower:
            return "High performance automated system"
        if "token" in name_lower:
            return "jwt.token.sample_string"
        if "telegram" in name_lower or "tg" in name_lower:
            return "123456789"
        if "user" in name_lower:
            return "john_doe"
        if "pass" in name_lower or "secret" in name_lower:
            return "SecurePass123!"
        if "date" in name_lower or "time" in name_lower or "at" in name_lower:
            return "2026-09-12T15:00:00.000Z"
        if "status" in name_lower:
            return "active"
        if "role" in name_lower:
            return "admin"
        if "id" in name_lower:
            return "usr_1001"

        return f"sample_{prop_name}"

    @staticmethod
    def build_mock_from_schema(schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Builds a complete mock JSON object from a schema definition."""
        if not schema or not isinstance(schema, dict):
            return {}
        
        props = schema.get("properties", {})
        mock_obj = {}
        for prop_name, prop_meta in props.items():
            if isinstance(prop_meta, dict):
                p_type = prop_meta.get("type", "string")
                mock_obj[prop_name] = BaseAdapter.generate_heuristic_mock(prop_name, p_type, prop_meta)
            else:
                mock_obj[prop_name] = BaseAdapter.generate_heuristic_mock(prop_name, str(prop_meta))
        return mock_obj
