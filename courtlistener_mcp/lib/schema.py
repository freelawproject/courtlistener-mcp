"""Build tool input schemas: endpoint ids, choice lists and shared
properties."""

import json
from typing import Any, cast

from courtlistener.models import ENDPOINTS

from courtlistener_mcp.settings import DEFAULT_NUM_RESULTS, MAX_NUM_RESULTS


def is_search_endpoint_id(endpoint_id: object) -> bool:
    """Whether *endpoint_id* names the search API (the `search` tool)."""
    return isinstance(endpoint_id, str) and (
        endpoint_id == "search" or endpoint_id.endswith("-search")
    )


def endpoint_ids() -> list[str]:
    """Valid endpoint_id values: the REST endpoints, not search."""
    return [
        endpoint.endpoint_id
        for endpoint in ENDPOINTS.values()
        if not is_search_endpoint_id(endpoint.endpoint_id)
    ]


def endpoint_id_property(description: str) -> dict:
    """Build the endpoint_id schema property."""
    return {
        "type": "string",
        "enum": endpoint_ids(),
        "description": (
            f"{description} Search is not an endpoint here; use the "
            "`search` tool."
        ),
    }


def num_results_property() -> dict:
    """Build the num_results schema property shared by the result tools."""
    return {
        "type": "integer",
        "description": (
            f"Number of results to return (1-{MAX_NUM_RESULTS}). "
            f"Defaults to {DEFAULT_NUM_RESULTS}."
        ),
        "minimum": 1,
        "maximum": MAX_NUM_RESULTS,
        "default": DEFAULT_NUM_RESULTS,
    }


# Choice lists too long to enumerate in schemas, by field name and the
# endpoints where the field carries that list; `get_choices` serves them.
LONG_CHOICE_FIELDS: dict[str, tuple[str, ...]] = {
    "court": ("search",),
    "dob_state": ("people", "search"),
    "dod_state": ("people",),
    "location_state": ("positions",),
    "position_type": ("positions",),
    "source": ("dockets",),
}


def is_long_choice_field(endpoint_id: str, field_name: str) -> bool:
    """Whether this field's choices are listed by `get_choices` instead."""
    return endpoint_id in LONG_CHOICE_FIELDS.get(field_name, ())


def long_choices(field_name: str) -> list[dict]:
    """The full choice list behind a `LONG_CHOICE_FIELDS` entry."""
    endpoint_id = LONG_CHOICE_FIELDS[field_name][0]
    model = next(m for m in ENDPOINTS.values() if m.endpoint_id == endpoint_id)
    extra = model.model_fields[field_name].json_schema_extra
    assert isinstance(extra, dict)  # for mypy
    return cast("list[dict]", extra["choices"])


def prepare_choices_str(
    choices, endpoint_id: str = "", field_name: str = "", snippet_count=5
):
    """Describe a field's choices: in full, or by example for long lists."""
    if not choices:
        return ""
    if is_long_choice_field(endpoint_id, field_name):
        snippet = ", ".join(
            f"{c['value']} ({c['display_name']})"
            for c in choices[:snippet_count]
        )
        return (
            f"This field has {len(choices)} valid choices. "
            f"Examples: {snippet}, ...\n\n"
            f"Use the `get_choices` tool with "
            f'field_name="{field_name}" to see all choices.'
        )
    return "Valid choices:\n\n" + json.dumps(choices, indent=2)


def strip_schema_keys(node, keys):
    """Recursively drop ``keys`` from every dict in a schema tree."""
    if isinstance(node, list):
        return [strip_schema_keys(item, keys) for item in node]
    if isinstance(node, dict):
        return {
            key: strip_schema_keys(value, keys)
            for key, value in node.items()
            if key not in keys
        }
    return node


def prepare_filter(
    filter: dict[str, Any], endpoint_id: str = "", field_name: str = ""
) -> dict[str, Any]:
    choices_str = prepare_choices_str(
        filter.get("choices"),
        endpoint_id=endpoint_id,
        field_name=field_name,
    )
    filter["description"] = (
        filter.get("description", "") + "\n\n" + choices_str
    ).strip()
    if "choices" in filter:
        del filter["choices"]
    return cast(
        "dict[str, Any]",
        strip_schema_keys(filter, {"title", "related_class_name", "default"}),
    )
