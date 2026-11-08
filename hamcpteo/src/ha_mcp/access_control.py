"""Per-category access levels for the AI client (HAMcpTeo / TeodorTeo.com).

Every Home Assistant entity belongs to a category (alarms, locks, security,
lights, climate, ...). Each category has one of three levels:

* ``none`` - the AI can neither see nor change it,
* ``read`` - the AI can see it but not change it,
* ``full`` - the AI can see and change it.

Calls that touch no entity (configuration, add-ons, restarts, files, ...) belong
to the ``system`` category. The levels live in ``access_levels.json`` in the data
directory and are edited on the ``/access`` page of the settings UI. Changes apply
on the next tool call, no restart needed.

Enforcement is a middleware: a call is checked against the entity ids and the
service domain found in its arguments, and results are scrubbed of entities in
``none`` categories. Targeting by area/device/label only (no entity id and no
domain) is classified as ``system``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from ha_mcp._vendor.fastmcp.server.middleware.middleware import (
    CallNext,
    Middleware,
    MiddlewareContext,
)

from .errors import ErrorCode, create_error_response
from .read_only import ReadOnlyMiddleware
from .renamed_tools import current_tool_name
from .tool_dispatch import CALL_PROXY_META_TOOLS
from .utils.data_paths import get_data_dir

if TYPE_CHECKING:
    from ha_mcp._vendor.fastmcp.tools import Tool

logger = logging.getLogger(__name__)

LEVELS = ("none", "read", "full")
SYSTEM = "system"
OTHER = "other"

# id, Polish label, English label, colour, domains, Polish hint, English hint, default level
CATEGORIES: tuple[dict[str, Any], ...] = (
    {
        "id": "alarms", "color": "#e53935", "default": "read",
        "pl": "Alarmy", "en": "Alarms",
        "domains": ["alarm_control_panel", "siren"],
        "hint_pl": "Centrala alarmowa, syreny", "hint_en": "Alarm panels, sirens",
    },
    {
        "id": "locks", "color": "#fb8c00", "default": "read",
        "pl": "Zamki", "en": "Locks",
        "domains": ["lock"],
        "hint_pl": "Zamki w drzwiach", "hint_en": "Door locks",
    },
    {
        "id": "security", "color": "#8e24aa", "default": "read",
        "pl": "Bezpieczeństwo", "en": "Security",
        "domains": ["camera", "device_tracker", "person", "image"],
        "hint_pl": "Kamery, lokalizacja osób, czujniki drzwi / okien / dymu / ruchu / zalania, bramy i garaże",
        "hint_en": "Cameras, people tracking, door / window / smoke / motion / leak sensors, gates and garages",
    },
    {
        "id": "covers", "color": "#5e35b1", "default": "full",
        "pl": "Rolety i okna", "en": "Covers",
        "domains": ["cover", "valve"],
        "hint_pl": "Rolety, żaluzje, markizy", "hint_en": "Blinds, shutters, awnings",
    },
    {
        "id": "climate", "color": "#1e88e5", "default": "full",
        "pl": "Klimat", "en": "Climate",
        "domains": ["climate", "water_heater", "fan", "humidifier", "vacuum", "lawn_mower"],
        "hint_pl": "Ogrzewanie, klimatyzacja, wentylatory, sprzątanie",
        "hint_en": "Heating, A/C, fans, cleaning",
    },
    {
        "id": "lights", "color": "#fdd835", "default": "full",
        "pl": "Światła", "en": "Lights",
        "domains": ["light"],
        "hint_pl": "Oświetlenie", "hint_en": "Lighting",
    },
    {
        "id": "switches", "color": "#00acc1", "default": "full",
        "pl": "Przełączniki", "en": "Switches",
        "domains": ["switch", "input_boolean", "input_button", "button", "remote"],
        "hint_pl": "Gniazdka, przełączniki, przyciski", "hint_en": "Plugs, switches, buttons",
    },
    {
        "id": "media", "color": "#ec407a", "default": "full",
        "pl": "Multimedia", "en": "Media",
        "domains": ["media_player", "tts", "stt", "assist_satellite", "notify"],
        "hint_pl": "Głośniki, telewizory, powiadomienia", "hint_en": "Speakers, TVs, notifications",
    },
    {
        "id": "automations", "color": "#43a047", "default": "full",
        "pl": "Automatyzacje", "en": "Automations",
        "domains": ["automation", "script", "scene", "timer", "schedule", "input_datetime",
                    "input_number", "input_select", "input_text", "counter", "todo", "calendar"],
        "hint_pl": "Automatyzacje, skrypty, sceny, pomocniki", "hint_en": "Automations, scripts, scenes, helpers",
    },
    {
        "id": "sensors", "color": "#78909c", "default": "full",
        "pl": "Czujniki", "en": "Sensors",
        "domains": ["sensor", "binary_sensor", "weather", "sun", "zone", "number", "select", "text"],
        "hint_pl": "Odczyty i stany (bez czujników bezpieczeństwa)",
        "hint_en": "Readings and states (without security sensors)",
    },
    {
        "id": OTHER, "color": "#8d6e63", "default": "full",
        "pl": "Pozostałe urządzenia", "en": "Other devices",
        "domains": [],
        "hint_pl": "Wszystko, czego nie ma wyżej", "hint_en": "Everything not listed above",
    },
    {
        "id": SYSTEM, "color": "#37474f", "default": "full",
        "pl": "System i konfiguracja", "en": "System & configuration",
        "domains": [],
        "hint_pl": "Edycja konfiguracji, dodatki, restarty, kopie zapasowe, pliki, dashboardy",
        "hint_en": "Configuration edits, add-ons, restarts, backups, files, dashboards",
    },
)

_DOMAIN_TO_CATEGORY: dict[str, str] = {
    d: c["id"] for c in CATEGORIES for d in c["domains"]
}
_CATEGORY_IDS = {c["id"] for c in CATEGORIES}

_ENTITY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")
_ENTITY_KEYS = {"entity_id", "entity_ids", "entity", "entities"}
_DOMAIN_KEYS = {"domain", "domain_filter", "domains"}
# Object-id words that make a sensor / cover / switch count as "security".
_SECURITY_WORDS = re.compile(
    r"(door|window|smoke|motion|gas|leak|flood|garage|gate|brama|drzwi|okno|dym|ruch|zalan|czad|alarm)"
)
_SECURITY_DOMAINS = {"binary_sensor", "sensor", "cover", "switch"}


def category_of_entity(entity_id: str) -> str:
    """Return the category id of ``entity_id`` (``domain.object_id``)."""
    domain, _, object_id = entity_id.partition(".")
    base = _DOMAIN_TO_CATEGORY.get(domain, OTHER)
    if domain in _SECURITY_DOMAINS and _SECURITY_WORDS.search(object_id):
        return "security"
    return base


def default_levels() -> dict[str, str]:
    return {c["id"]: c["default"] for c in CATEGORIES}


def _config_path() -> Any:
    return get_data_dir() / "access_levels.json"


_cache: tuple[float, dict[str, str]] | None = None


def load_levels() -> dict[str, str]:
    """Return ``{category: level}``; unknown / missing entries use the defaults."""
    global _cache
    path = _config_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0
    if _cache is not None and _cache[0] == mtime:
        return dict(_cache[1])
    levels = default_levels()
    if mtime >= 0:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for cat, level in (raw.get("levels") or {}).items():
                if cat in _CATEGORY_IDS and level in LEVELS:
                    levels[cat] = level
        except (OSError, ValueError, AttributeError):
            logger.warning("access_levels.json unreadable - using defaults")
    _cache = (mtime, levels)
    return dict(levels)


def save_levels(levels: dict[str, Any]) -> dict[str, str]:
    """Validate and persist ``levels``; returns the effective mapping."""
    global _cache
    merged = load_levels()
    for cat, level in levels.items():
        if cat in _CATEGORY_IDS and level in LEVELS:
            merged[cat] = level
    path = _config_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"levels": merged}, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    _cache = None
    return merged


def catalog() -> list[dict[str, Any]]:
    """Category metadata for the UI."""
    return [
        {k: c[k] for k in ("id", "color", "pl", "en", "hint_pl", "hint_en", "default")}
        for c in CATEGORIES
    ]


# --------------------------------------------------------------------- targets


def _add_entities(value: Any, out: set[str]) -> None:
    if isinstance(value, str):
        for part in value.split(","):
            part = part.strip()
            if _ENTITY_RE.match(part):
                out.add(category_of_entity(part))
    elif isinstance(value, (list, tuple)):
        for item in value:
            _add_entities(item, out)
    elif isinstance(value, dict):
        for item in value.values():
            _add_entities(item, out)


def _walk(obj: Any, out: set[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in _ENTITY_KEYS:
                _add_entities(value, out)
            elif key in _DOMAIN_KEYS:
                for dom in value if isinstance(value, list) else [value]:
                    if isinstance(dom, str) and dom in _DOMAIN_TO_CATEGORY:
                        out.add(_DOMAIN_TO_CATEGORY[dom])
                if isinstance(value, dict):
                    _walk(value, out)
            else:
                _walk(value, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, out)
    elif isinstance(obj, str) and _ENTITY_RE.match(obj):
        if obj.split(".", 1)[0] in _DOMAIN_TO_CATEGORY:
            out.add(category_of_entity(obj))


def categories_for_call(args: dict[str, Any]) -> set[str]:
    """Categories a call touches; ``{system}`` when it names no entity or domain."""
    found: set[str] = set()
    _walk(args, found)
    return found or {SYSTEM}


# --------------------------------------------------------------------- results


def _hidden(entity_id: Any, hidden_cats: set[str]) -> bool:
    return (
        isinstance(entity_id, str)
        and bool(_ENTITY_RE.match(entity_id))
        and category_of_entity(entity_id) in hidden_cats
    )


def _scrub(obj: Any, hidden_cats: set[str]) -> Any:
    """Drop every entity of a hidden category from a JSON-like structure."""
    if isinstance(obj, list):
        return [
            _scrub(i, hidden_cats)
            for i in obj
            if not (isinstance(i, dict) and _hidden(i.get("entity_id"), hidden_cats))
            and not _hidden(i, hidden_cats)
        ]
    if isinstance(obj, dict):
        return {
            k: _scrub(v, hidden_cats)
            for k, v in obj.items()
            if not _hidden(k, hidden_cats)
            and not (isinstance(v, dict) and _hidden(v.get("entity_id"), hidden_cats))
        }
    return obj


# ------------------------------------------------------------------ middleware


class AccessControlMiddleware(Middleware):
    """Enforce the per-category levels on every tool call."""

    def __init__(self, *, list_tools: Callable[[], Awaitable[Sequence[Tool]]]) -> None:
        self._classifier = ReadOnlyMiddleware(list_tools=list_tools)

    async def on_call_tool(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        levels = load_levels()
        name = current_tool_name(context.message.name)
        args = context.message.arguments or {}
        inner_name = name
        if name in CALL_PROXY_META_TOOLS:
            unwrapped = ReadOnlyMiddleware._unwrap_proxy_call(args)
            if unwrapped is None:
                return await call_next(context)
            inner_name, args = unwrapped
            inner_name = current_tool_name(inner_name)

        kind = await self._classifier._classify(inner_name)
        if kind == "unknown":
            return await call_next(context)

        need = "full" if kind == "write" else "read"
        for cat in sorted(categories_for_call(args)):
            level = levels.get(cat, "full")
            if LEVELS.index(level) < LEVELS.index(need):
                self._deny(inner_name, cat, level, need)

        result = await call_next(context)

        hidden = {c for c, lv in levels.items() if lv == "none"}
        if hidden:
            for block in getattr(result, "content", None) or []:
                text = getattr(block, "text", None)
                if isinstance(text, str) and text[:1] in "{[":
                    try:
                        data = json.loads(text)
                    except ValueError:
                        continue
                    scrubbed = _scrub(data, hidden)
                    if scrubbed != data:
                        block.text = json.dumps(scrubbed, ensure_ascii=False)
            structured = getattr(result, "structured_content", None)
            if structured is not None:
                result.structured_content = _scrub(structured, hidden)
        return result

    @staticmethod
    def _deny(tool: str, category: str, level: str, need: str) -> None:
        from .tools.helpers import raise_tool_error

        meta = next(c for c in CATEGORIES if c["id"] == category)
        action = "change" if need == "full" else "see"
        raise_tool_error(
            create_error_response(
                ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS,
                f"Access level for '{meta['en']}' is '{level}': the AI is not allowed "
                f"to {action} this. Nothing was done by '{tool}'.",
                suggestions=[
                    "Ask the owner to change the level on the Access page of the "
                    "HAMcpTeo panel (TeodorTeo.com).",
                ],
                context={"category": category, "level": level, "tool_name": tool},
            )
        )
