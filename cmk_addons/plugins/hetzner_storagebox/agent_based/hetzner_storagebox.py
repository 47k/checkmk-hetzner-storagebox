#!/usr/bin/env python3
"""Agent based check for Hetzner Storage Boxes."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, TypedDict

from cmk.agent_based.v2 import AgentSection, CheckPlugin, Metric, Result, Service, State

ACTIVE_STATUSES = {"active", "available", "ok", "online", "ready", "running"}
Levels = tuple[float, float]
LevelViolation = tuple[State, float]


class ErrorInfo(TypedDict):
    code: str
    message: str


class Section(TypedDict):
    boxes: dict[str, dict[str, Any]]
    errors: list[ErrorInfo]


class DisplayField(TypedDict):
    text: str
    state: State


def parse_hetzner_storagebox(string_table: list[list[str]]) -> Section | None:
    if not string_table:
        return {"boxes": {}, "errors": [{"code": "no_data", "message": "No agent data received"}]}

    raw_payload = "".join(cell for row in string_table for cell in row).strip()
    if not raw_payload:
        return {"boxes": {}, "errors": [{"code": "no_data", "message": "Empty agent section"}]}

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        return {"boxes": {}, "errors": [{"code": "json_error", "message": f"Invalid JSON in agent section: {exc}"}]}

    if not isinstance(payload, dict):
        return {"boxes": {}, "errors": [{"code": "payload_error", "message": "Agent payload is not a JSON object"}]}

    storage_boxes = payload.get("storage_boxes", [])
    errors = _normalize_errors(payload.get("errors", []))

    if not isinstance(storage_boxes, list):
        return {
            "boxes": {},
            "errors": errors
            + [{"code": "payload_error", "message": "Agent payload field 'storage_boxes' is not a list"}],
        }

    boxes = _storage_boxes_by_item(storage_boxes)
    return {"boxes": boxes, "errors": errors}


def _normalize_errors(raw_errors: Any) -> list[ErrorInfo]:
    if raw_errors in (None, ""):
        return []
    if not isinstance(raw_errors, list):
        return [{"code": "payload_error", "message": "Agent payload field 'errors' is not a list"}]

    errors: list[ErrorInfo] = []
    for raw_error in raw_errors:
        if isinstance(raw_error, dict):
            code = str(raw_error.get("code") or "error")
            message = str(raw_error.get("message") or "Agent reported an API error")
        else:
            code = "error"
            message = str(raw_error)
        errors.append({"code": code, "message": message})
    return errors


def _storage_boxes_by_item(raw_storage_boxes: list[Any]) -> dict[str, dict[str, Any]]:
    valid_boxes = [storage_box for storage_box in raw_storage_boxes if isinstance(storage_box, dict)]
    base_names = [_base_item_name(storage_box) for storage_box in valid_boxes]
    duplicate_names = {name for name in base_names if base_names.count(name) > 1}

    boxes: dict[str, dict[str, Any]] = {}
    for index, storage_box in enumerate(valid_boxes):
        item_name = _base_item_name(storage_box)
        if item_name in duplicate_names:
            box_id = storage_box.get("id")
            item_name = f"{item_name} ({box_id})" if box_id not in (None, "") else f"{item_name} ({index + 1})"
        boxes[item_name] = storage_box
    return boxes


def _base_item_name(storage_box: Mapping[str, Any]) -> str:
    for key in ("username", "id"):
        value = storage_box.get(key)
        if value not in (None, ""):
            return str(value)
    return "unknown"


agent_section_hetzner_storagebox = AgentSection(
    name="hetzner_storagebox",
    parse_function=parse_hetzner_storagebox,
)


def discover_hetzner_storagebox(section: Section) -> Iterable[Service]:
    for item in sorted(section["boxes"]):
        yield Service(item=item)


def check_hetzner_storagebox(item: str, params: Mapping[str, Any], section: Section | None) -> Iterable[Result | Metric]:
    if section is None:
        yield Result(state=State.CRIT, summary="No data received")
        return

    storage_box = section["boxes"].get(item)
    api_error_state = _state_from_params(params, "api_error_state", State.UNKNOWN)
    if storage_box is None:
        if section["errors"]:
            yield Result(
                state=api_error_state,
                summary=_format_errors(section["errors"]),
            )
            return
        yield Result(state=State.UNKNOWN, summary="Storage Box not found in current agent data")
        return

    usage_levels = _usage_levels(params)
    used_bytes = _number_at(storage_box, ("stats", "size"))
    total_bytes = _number_at(storage_box, ("storage_box_type", "size"))
    data_bytes = _number_at(storage_box, ("stats", "size_data"))
    snapshots_bytes = _number_at(storage_box, ("stats", "size_snapshots"))
    snapshots_count = _number_at(storage_box, ("snapshots_count",))
    subaccounts_count = _number_at(storage_box, ("subaccounts_count",))
    subaccounts_error = _error_at(storage_box, "subaccounts_error")

    snapshot_size_levels = _optional_levels(params, "snapshot_size_levels")
    snapshot_count_levels = _optional_levels(params, "snapshot_count_levels")
    subaccounts_count_levels = _optional_levels(params, "subaccounts_count_levels")
    snapshot_size_violation = _level_violation(snapshots_bytes, snapshot_size_levels)
    snapshot_count_violation = _level_violation(snapshots_count, snapshot_count_levels)
    subaccounts_count_violation = _level_violation(subaccounts_count, subaccounts_count_levels)

    status = _string_at(storage_box, ("status",)) or "unknown"
    status_state = State.OK if status.lower() in ACTIVE_STATUSES else _state_from_params(params, "status_state", State.WARN)

    usage_percent = _usage_percent(used_bytes, total_bytes)
    usage_state = _usage_state(usage_percent, usage_levels)
    subaccounts_error_state = api_error_state if subaccounts_error is not None else State.OK
    fields = _display_fields(
        status=status,
        status_state=status_state,
        used_bytes=used_bytes,
        total_bytes=total_bytes,
        usage_percent=usage_percent,
        usage_state=usage_state,
        snapshots_bytes=snapshots_bytes,
        snapshots_count=snapshots_count,
        subaccounts_count=subaccounts_count,
        snapshot_size_violation=snapshot_size_violation,
        snapshot_count_violation=snapshot_count_violation,
        subaccounts_count_violation=subaccounts_count_violation,
        subaccounts_error_state=subaccounts_error_state,
        api_errors=section["errors"],
        api_error_state=api_error_state,
    )

    for field in fields:
        yield Result(state=field["state"], summary=field["text"])

    yield from _metrics(
        usage_levels=usage_levels,
        snapshot_size_levels=snapshot_size_levels,
        snapshot_count_levels=snapshot_count_levels,
        subaccounts_count_levels=subaccounts_count_levels,
        used_bytes=used_bytes,
        total_bytes=total_bytes,
        usage_percent=usage_percent,
        data_bytes=data_bytes,
        snapshots_bytes=snapshots_bytes,
        snapshots_count=snapshots_count,
        subaccounts_count=subaccounts_count,
    )


def _format_errors(errors: list[ErrorInfo]) -> str:
    summary = _format_error("API error", errors[0])
    if len(errors) > 1:
        summary += f" (+{len(errors) - 1} more)"
    return summary


def _format_error(prefix: str, error: ErrorInfo) -> str:
    return f"{prefix} ({error['code']}): {error['message']}"


def _display_fields(
    *,
    status: str,
    status_state: State,
    used_bytes: float | None,
    total_bytes: float | None,
    usage_percent: float | None,
    usage_state: State,
    snapshots_bytes: float | None,
    snapshots_count: float | None,
    subaccounts_count: float | None,
    snapshot_size_violation: LevelViolation | None,
    snapshot_count_violation: LevelViolation | None,
    subaccounts_count_violation: LevelViolation | None,
    subaccounts_error_state: State,
    api_errors: list[ErrorInfo],
    api_error_state: State,
) -> list[DisplayField]:
    parts: list[DisplayField] = []
    if used_bytes is not None and total_bytes not in (None, 0) and usage_percent is not None:
        parts.append(
            _display_field(
                f"Used {usage_percent:.1f}% ({_format_bytes(used_bytes)} / {_format_bytes(total_bytes)})",
                usage_state,
            )
        )
    else:
        parts.append(_display_field("Usage data incomplete", usage_state))

    parts.append(_display_field(f"Status: {_format_status(status)}", status_state))

    if snapshots_bytes is not None:
        parts.append(
            _display_field("Snapshot size " + _format_bytes(snapshots_bytes), _violation_state(snapshot_size_violation))
        )

    if snapshots_count is not None:
        parts.append(
            _display_field("Snapshot count " + _format_count(snapshots_count), _violation_state(snapshot_count_violation))
        )
    else:
        parts.append(_display_field("Snapshot count n/a"))

    if subaccounts_count is not None:
        parts.append(
            _display_field(
                "Subaccounts " + _format_count(subaccounts_count),
                _worst_state(_violation_state(subaccounts_count_violation), subaccounts_error_state),
            )
        )
    else:
        parts.append(_display_field("Subaccounts n/a", subaccounts_error_state))

    if api_errors:
        text = _format_error("API error", api_errors[0])
        if len(api_errors) > 1:
            text += f" (+{len(api_errors) - 1} more)"
        parts.append(_display_field(text, api_error_state))

    return parts


def _display_field(text: str, state: State = State.OK) -> DisplayField:
    return {"text": text, "state": state}


def _metrics(
    *,
    usage_levels: Levels | None,
    snapshot_size_levels: Levels | None,
    snapshot_count_levels: Levels | None,
    subaccounts_count_levels: Levels | None,
    used_bytes: float | None,
    total_bytes: float | None,
    usage_percent: float | None,
    data_bytes: float | None,
    snapshots_bytes: float | None,
    snapshots_count: float | None,
    subaccounts_count: float | None,
) -> Iterable[Metric]:
    if used_bytes is not None:
        yield Metric("used_bytes", used_bytes)
    if total_bytes is not None:
        yield Metric("total_bytes", total_bytes)
    if usage_percent is not None:
        yield Metric("used_percent", usage_percent, levels=usage_levels, boundaries=(0.0, 100.0))
    if data_bytes is not None:
        yield Metric("data_bytes", data_bytes)
    if snapshots_bytes is not None:
        yield Metric("snapshots_bytes", snapshots_bytes, levels=snapshot_size_levels)
    if snapshots_count is not None:
        yield Metric("snapshots_count", snapshots_count, levels=snapshot_count_levels)
    if subaccounts_count is not None:
        yield Metric("subaccounts_count", subaccounts_count, levels=subaccounts_count_levels)


def _usage_percent(used_bytes: float | None, total_bytes: float | None) -> float | None:
    if used_bytes is None or total_bytes in (None, 0):
        return None
    return used_bytes / total_bytes * 100.0


def _usage_state(usage_percent: float | None, levels: tuple[float, float] | None) -> State:
    if usage_percent is None:
        return State.UNKNOWN
    if levels is None:
        return State.OK
    warn, crit = levels
    if usage_percent >= crit:
        return State.CRIT
    if usage_percent >= warn:
        return State.WARN
    return State.OK


def _usage_levels(params: Mapping[str, Any]) -> Levels | None:
    levels = params.get("usage_levels")
    parsed_levels = _levels_from_value(levels)
    if parsed_levels is not None or _is_no_levels(levels):
        return parsed_levels

    warn = params.get("warn", params.get("usage_warn", 80.0))
    crit = params.get("crit", params.get("usage_crit", 90.0))
    return (float(warn), float(crit))


def _optional_levels(params: Mapping[str, Any], key: str) -> Levels | None:
    return _levels_from_value(params.get(key))


def _levels_from_value(levels: Any) -> Levels | None:
    if isinstance(levels, (tuple, list)) and len(levels) == 2:
        level_type, values = levels
        if level_type == "no_levels":
            return None
        if level_type == "fixed" and isinstance(values, (tuple, list)) and len(values) == 2:
            return (float(values[0]), float(values[1]))
    return None


def _is_no_levels(levels: Any) -> bool:
    return isinstance(levels, (tuple, list)) and len(levels) == 2 and levels[0] == "no_levels"


def _level_violation(value: float | None, levels: Levels | None) -> LevelViolation | None:
    if value is None or levels is None:
        return None

    warn, crit = levels
    if value >= crit:
        return State.CRIT, crit
    if value >= warn:
        return State.WARN, warn
    return None


def _violation_state(violation: LevelViolation | None) -> State:
    if violation is None:
        return State.OK
    state, _level = violation
    return state


def _number_at(data: Mapping[str, Any], path: tuple[str, ...]) -> float | None:
    value: Any = data
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)

    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_at(data: Mapping[str, Any], path: tuple[str, ...]) -> str | None:
    value: Any = data
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    if value in (None, ""):
        return None
    return str(value)


def _error_at(data: Mapping[str, Any], key: str) -> ErrorInfo | None:
    value = data.get(key)
    if not isinstance(value, Mapping):
        return None
    return {
        "code": str(value.get("code") or "error"),
        "message": str(value.get("message") or "API error"),
    }


def _state_from_params(params: Mapping[str, Any], key: str, default: State) -> State:
    raw_state = params.get(key)
    if raw_state is None:
        return default
    return {
        "OK": State.OK,
        "WARN": State.WARN,
        "WARNING": State.WARN,
        "CRIT": State.CRIT,
        "CRITICAL": State.CRIT,
        "UNKNOWN": State.UNKNOWN,
    }.get(str(raw_state).upper(), default)


def _worst_state(*states: State) -> State:
    ranking = {State.OK: 0, State.WARN: 1, State.UNKNOWN: 2, State.CRIT: 3}
    return max(states, key=lambda state: ranking[state])


def _format_status(status: str) -> str:
    if status.lower() == "ok":
        return "OK"
    return " ".join(part.capitalize() for part in status.replace("_", " ").replace("-", " ").split()) or "Unknown"


def _format_bytes(value: float) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    amount = float(value)
    unit = units[0]
    for unit in units:
        if abs(amount) < 1024.0 or unit == units[-1]:
            break
        amount /= 1024.0
    return f"{amount:.2f} {unit}" if unit != "B" else f"{amount:.0f} {unit}"


def _format_count(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


check_plugin_hetzner_storagebox = CheckPlugin(
    name="hetzner_storagebox",
    service_name="Hetzner Storage Box %s",
    discovery_function=discover_hetzner_storagebox,
    check_function=check_hetzner_storagebox,
    check_default_parameters={
        "usage_levels": ("fixed", (80.0, 90.0)),
        "status_state": "WARN",
        "api_error_state": "UNKNOWN",
    },
    check_ruleset_name="hetzner_storagebox",
)
