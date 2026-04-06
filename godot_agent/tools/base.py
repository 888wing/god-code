from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    name: str
    description: str
    Input: type[BaseModel]
    Output: type[BaseModel]

    @abstractmethod
    async def execute(self, input: BaseModel) -> ToolResult:
        ...

    def is_read_only(self) -> bool:
        """Fail-closed default: assume tool may modify state."""
        return False

    def is_destructive(self) -> bool:
        """Fail-closed default: assume tool can be destructive."""
        return True

    def is_concurrency_safe(self) -> bool:
        """Fail-closed default: assume tool is not concurrency safe."""
        return False

    def validate_input(self, input: BaseModel) -> str | None:
        """Optional business-level validation after schema parsing."""
        return None

    def to_openai_schema(self, strict: bool = False) -> dict:
        params = self.Input.model_json_schema()
        schema: dict = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
        }
        if strict:
            # OpenAI strict mode cannot represent two pydantic patterns:
            # ``dict[str, Any]`` (free-form object, no closed property list)
            # and ``Any`` (typeless schema). If this tool has either, drop
            # strict for *this* tool so the LLM still gets the schema —
            # other tools keep strict mode unaffected.
            if _has_strict_incompatible_node(params):
                schema["function"]["strict"] = False
            else:
                schema["function"]["strict"] = True
                _enforce_strict_object_schema(params)
                for def_schema in (params.get("$defs") or {}).values():
                    _enforce_strict_object_schema(def_schema)
        return schema


def _is_typeless_schema(node: dict) -> bool:
    """Return True if *node* is a schema with no concrete ``type``.

    Pydantic emits ``Any`` fields as a schema with no ``type`` key (often
    with only ``description``/``title``). OpenAI strict mode requires
    every property to have a ``type``, so such tools cannot use strict.
    """
    if "type" in node:
        return False
    if "anyOf" in node or "oneOf" in node or "allOf" in node:
        return False
    if "$ref" in node or "enum" in node:
        return False
    return True


def _has_strict_incompatible_node(node: Any) -> bool:
    """Return True if *node* contains any sub-schema OpenAI strict cannot accept.

    Two patterns trigger this:
    - Free-form object (``{"type": "object"}`` with no ``properties``):
      pydantic's representation of ``dict[str, Any]``. Strict requires a
      closed property list, which cannot be expressed.
    - Typeless schema (no ``type`` key, no composition keyword): pydantic's
      representation of ``Any``. Strict requires a concrete type.
    """
    if not isinstance(node, dict):
        return False
    if node.get("type") == "object" and "properties" not in node:
        return True
    properties = node.get("properties")
    if isinstance(properties, dict):
        for child in properties.values():
            if isinstance(child, dict) and _is_typeless_schema(child):
                return True
            if _has_strict_incompatible_node(child):
                return True
    for key in ("items", "anyOf", "oneOf", "allOf"):
        value = node.get(key)
        if isinstance(value, list):
            if any(_has_strict_incompatible_node(item) for item in value):
                return True
        elif isinstance(value, dict):
            if _has_strict_incompatible_node(value):
                return True
    for def_schema in (node.get("$defs") or {}).values():
        if _has_strict_incompatible_node(def_schema):
            return True
    return False


# Backwards-compatible alias kept so external callers (if any) keep working.
_has_freeform_object = _has_strict_incompatible_node


def _enforce_strict_object_schema(node: Any) -> None:
    """Recursively make a JSON-Schema fragment OpenAI-strict-mode compliant.

    OpenAI's structured-output / strict tool mode rejects any object schema
    that does not declare ``additionalProperties: false`` and list every
    property in ``required``. Pydantic omits ``required`` for fields with
    defaults, which trips the validator. Walk the schema and patch every
    object node we own. Tools with free-form dict fields are filtered out
    upstream by ``_has_freeform_object`` because strict cannot represent
    them at all.
    """
    if not isinstance(node, dict):
        return
    if node.get("type") == "object":
        node["additionalProperties"] = False
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["required"] = sorted(properties.keys())
            for child in properties.values():
                _enforce_strict_object_schema(child)
    for key in ("items", "anyOf", "oneOf", "allOf"):
        value = node.get(key)
        if isinstance(value, list):
            for item in value:
                _enforce_strict_object_schema(item)
        elif isinstance(value, dict):
            _enforce_strict_object_schema(value)
