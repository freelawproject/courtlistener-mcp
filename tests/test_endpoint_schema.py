"""Tests for get_endpoint_schema output and $ref inlining."""

from __future__ import annotations

import asyncio
import json

import pytest
from courtlistener.models import ENDPOINTS

from courtlistener_mcp.lib.schema import endpoint_model, endpoint_name
from courtlistener_mcp.tools import MCP_TOOLS


def _schema(endpoint_id: str) -> dict:
    tool = MCP_TOOLS["get_endpoint_schema"]
    return asyncio.run(tool.call({"endpoint_id": endpoint_id}))


def _non_search_endpoint_ids() -> list[str]:
    ids: list[str] = []
    for endpoint in ENDPOINTS.values():
        eid = endpoint.endpoint_id
        if eid == "search" or eid.endswith("-search"):
            continue
        if eid not in ids:
            ids.append(eid)
    return ids


class TestEndpointSchemaOutput:
    def test_no_dangling_refs_anywhere(self):
        """No endpoint schema may contain a $ref key or a #/$defs pointer."""
        for eid in _non_search_endpoint_ids():
            payload = json.dumps(_schema(eid))
            assert '"$ref"' not in payload, f"{eid} has a $ref key"
            assert "#/$defs" not in payload, (
                f"{eid} has a dangling $defs pointer"
            )

    def test_filter_lookups_are_inlined(self):
        """A string field should carry its lookup operators inline."""
        schema = _schema("courts")
        full_name = schema["properties"]["full_name"]
        branches = full_name["anyOf"]
        filter_branch = next(b for b in branches if b.get("type") == "object")
        assert "iexact" in filter_branch["properties"]
        assert "startswith" in filter_branch["properties"]

    def test_schema_noise_is_stripped(self):
        """Inlined defs must not carry title/default/related_class_name."""
        schema = _schema("courts")

        def has_noise(node) -> bool:
            if isinstance(node, dict):
                if {"title", "default", "related_class_name"} & node.keys():
                    return True
                return any(has_noise(v) for v in node.values())
            if isinstance(node, list):
                return any(has_noise(v) for v in node)
            return False

        for field_schema in schema["properties"].values():
            assert not has_noise(field_schema)

    def test_legitimate_title_field_is_preserved(self):
        """A real column named 'title' must survive (not stripped as noise)."""
        schema = _schema("fjc-integrated-database")
        assert "title" in schema["properties"]


class TestEndpointLookup:
    def test_every_endpoint_is_found_by_id(self):
        for name, model in ENDPOINTS.items():
            assert endpoint_name(model.endpoint_id) == name
            assert endpoint_model(model.endpoint_id) is model

    def test_id_differs_from_client_attribute(self):
        assert endpoint_name("docket-entries") == "docket_entries"

    @pytest.mark.parametrize(
        "tool_name",
        ["call_endpoint", "get_endpoint_item", "get_endpoint_schema"],
    )
    def test_unknown_id_raises(self, tool_name):
        tool = MCP_TOOLS[tool_name]
        with pytest.raises(ValueError, match="Endpoint 'nope' not found"):
            asyncio.run(tool.call({"endpoint_id": "nope", "item_id": 1}))
