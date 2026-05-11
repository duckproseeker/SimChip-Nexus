from __future__ import annotations

from collections import defaultdict

UNSUPPORTED_MAP_NAME_KEYWORDS: tuple[str, ...] = (
    "annotationcolor",
    "annotation_color",
    "landscape",
    "testmap",
)

KNOWN_OPTIMIZED_MAP_REQUESTS: dict[str, str] = {
    "town01": "Town01_Opt",
    "town02": "Town02_Opt",
    "town03": "Town03_Opt",
    "town04": "Town04_Opt",
    "town05": "Town05_Opt",
    "town10": "Town10HD_Opt",
    "town10hd": "Town10HD_Opt",
}

FALLBACK_RUNTIME_MAPS: tuple[str, ...] = tuple(
    dict.fromkeys(KNOWN_OPTIMIZED_MAP_REQUESTS.values())
)


def normalize_map_tail(map_name: str) -> str:
    normalized = str(map_name).strip().rstrip("/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", maxsplit=1)[-1]
    return normalized


def map_family_key(map_name: str) -> str:
    normalized = normalize_map_tail(map_name).lower()
    if normalized.endswith("_opt"):
        normalized = normalized[:-4]
    if normalized == "town10":
        return "town10hd"
    return normalized


def display_map_name(map_name: str) -> str:
    normalized = normalize_map_tail(map_name)
    if normalized.lower().endswith("_opt"):
        return normalized[:-4]
    return normalized


def prefer_optimized_map_request(map_name: str) -> str:
    normalized = normalize_map_tail(map_name)
    return KNOWN_OPTIMIZED_MAP_REQUESTS.get(map_family_key(normalized), normalized)


def is_supported_runtime_map(map_name: str) -> bool:
    normalized = normalize_map_tail(map_name).lower()
    if not normalized:
        return False
    if normalized.startswith("town"):
        return True
    return not any(keyword in normalized for keyword in UNSUPPORTED_MAP_NAME_KEYWORDS)


def choose_preferred_available_map(candidates: list[str]) -> str:
    if not candidates:
        raise ValueError("candidates must not be empty")

    return sorted(
        candidates,
        key=lambda item: (
            not normalize_map_tail(item).lower().endswith("_opt"),
            len(normalize_map_tail(item)),
            normalize_map_tail(item).lower(),
        ),
    )[0]


def collapse_available_maps(available_maps: list[str]) -> list[dict[str, object]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for map_name in available_maps:
        if not is_supported_runtime_map(map_name):
            continue
        grouped[map_family_key(map_name)].append(map_name)

    items: list[dict[str, object]] = []
    for family_key, candidates in grouped.items():
        preferred = choose_preferred_available_map(candidates)
        normalized_variants = sorted({normalize_map_tail(item) for item in candidates})
        items.append(
            {
                "map_name": prefer_optimized_map_request(preferred),
                "display_name": display_map_name(preferred),
                "available_variants": normalized_variants,
                "preferred_variant": (
                    "optimized"
                    if normalize_map_tail(preferred).lower().endswith("_opt")
                    else "standard"
                ),
                "family_key": family_key,
            }
        )

    items.sort(key=lambda item: (str(item["display_name"]), str(item["map_name"])))
    return items


def fallback_runtime_map_options() -> list[dict[str, object]]:
    return collapse_available_maps(list(FALLBACK_RUNTIME_MAPS))
