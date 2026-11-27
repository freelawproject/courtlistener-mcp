from mcp.types import ToolAnnotations

from courtlistener_mcp.lib.results import normalize_fields
from courtlistener_mcp.lib.schema import endpoint_id_property, endpoint_name
from courtlistener_mcp.tools.base import MCPTool


class GetEndpointItemTool(MCPTool):
    """Get an item by ID from a CourtListener API endpoint."""

    name: str = "get_endpoint_item"
    annotations: ToolAnnotations = ToolAnnotations(
        title="Get Item by ID",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def get_input_schema(self) -> dict:
        """Get the input schema for the get_endpoint_item tool."""
        return {
            "type": "object",
            "properties": {
                "endpoint_id": endpoint_id_property(
                    "The endpoint to get an item from."
                ),
                "item_id": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "integer"},
                    ],
                    "description": "The ID of the item to get.",
                },
                "fields": {
                    "anyOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "string"},
                        {"type": "null"},
                    ],
                    "description": (
                        "Filter which fields are returned. Use the field "
                        "names from the endpoint's own schema (see the "
                        "`get_endpoint_schema` tool), not the field names "
                        "returned by the `search` tool."
                    ),
                },
            },
            "required": ["endpoint_id", "item_id"],
            "additionalProperties": False,
        }

    async def call(self, arguments: dict) -> dict:
        """Call the get_endpoint_item tool."""
        endpoint_id = arguments["endpoint_id"]
        item_id = arguments.get("item_id")
        fields = normalize_fields(arguments.get("fields"))

        resource_name = endpoint_name(endpoint_id)
        async with self.get_client() as client:
            resource = getattr(client, resource_name)
            return await resource.get(item_id, fields=fields)
