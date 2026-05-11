from __future__ import annotations

from typing import Any

from app.scenario.launch_builder import default_launch_capabilities
from app.scenario.official_runner import list_official_openscenario_catalog
from app.scenario.platform_catalog import list_platform_scenario_catalog
from app.scenario.template_registry import (
    build_template_parameter_schema,
    get_template_category,
)


def _catalog_source_items() -> list[dict[str, Any]]:
    return [
        *list_platform_scenario_catalog(),
        *list_official_openscenario_catalog(),
    ]


def list_scenario_catalog(*, include_hidden: bool = False) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in _catalog_source_items():
        enriched = dict(item)
        if bool(enriched.get("web_hidden")) and not include_hidden:
            continue
        existing_capabilities = enriched.get("launch_capabilities")
        if not isinstance(existing_capabilities, dict):
            existing_capabilities = default_launch_capabilities(map_editable=False)
        enriched["launch_capabilities"] = existing_capabilities
        enriched["category"] = get_template_category(enriched["scenario_id"])
        enriched["parameter_schema"] = build_template_parameter_schema(
            enriched["scenario_id"],
            enriched.get("parameter_declarations", []),
        )
        items.append(enriched)
    return items


def get_scenario_catalog_item(
    scenario_id: str, *, include_hidden: bool = True
) -> dict[str, Any] | None:
    normalized = scenario_id.strip()
    for item in list_scenario_catalog(include_hidden=include_hidden):
        if item["scenario_id"] == normalized:
            return item
    return None
