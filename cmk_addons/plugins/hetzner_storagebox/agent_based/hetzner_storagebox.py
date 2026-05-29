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
ACCESS_SETTINGS = (
    ("expected_samba_access", ("access_settings", "samba_enabled"), "Samba"),
    ("expected_ssh_access", ("access_settings", "ssh_enabled"), "SSH"),
    ("expected_webdav_access", ("access_settings", "webdav_enabled"), "WebDAV"),
    ("expected_zfs_access", ("access_settings", "zfs_enabled"), "ZFS"),
    ("expected_external_reachability", ("access_settings", "reachable_externally"), "External"),
)
EXPECTED_BOOL_VALUES = {"enabled": True, "disabled": False}
MISSING = object()
HIDDEN_DETAILS = " "


class ErrorInfo(TypedDict):
    code: str
    message: str


class Section(TypedDict):
    boxes: dict[str, dict[str, Any]]
    errors: list[ErrorInfo]


class DisplayField(TypedDict):
    text: str
    details: str
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
        yield _summary_result(State.CRIT, "No data received")
        return

    storage_box = section["boxes"].get(item)
    api_error_state = _state_from_params(params, "api_error_state", State.UNKNOWN)
    if storage_box is None:
        if section["errors"]:
            yield _summary_result(api_error_state, _format_errors(section["errors"]))
            return
        yield _summary_result(State.UNKNOWN, "Storage Box not found in current agent data")
        return

    usage_levels = _usage_levels(params)
    used_bytes = _number_at(storage_box, ("stats", "size"))
    total_bytes = _number_at(storage_box, ("storage_box_type", "size"))
    data_bytes = _number_at(storage_box, ("stats", "size_data"))
    snapshots_bytes = _number_at(storage_box, ("stats", "size_snapshots"))
    snapshots_count = _number_at(storage_box, ("snapshots_count",))
    subaccounts_count = _number_at(storage_box, ("subaccounts_count",))
    subaccounts_error = _error_at(storage_box, "subaccounts_error")
    snapshot_limit = _number_at(storage_box, ("storage_box_type", "snapshot_limit"))
    subaccounts_limit = _number_at(storage_box, ("storage_box_type", "subaccounts_limit"))

    snapshot_size_levels = _optional_levels(params, "snapshot_size_levels")
    snapshot_count_levels = _optional_levels(params, "snapshot_count_levels")
    subaccounts_count_levels = _optional_levels(params, "subaccounts_count_levels")
    snapshot_limit_usage_levels = _optional_levels(params, "snapshot_limit_usage_levels")
    subaccount_limit_usage_levels = _optional_levels(params, "subaccount_limit_usage_levels")
    snapshot_size_violation = _level_violation(snapshots_bytes, snapshot_size_levels)
    snapshot_count_violation = _level_violation(snapshots_count, snapshot_count_levels)
    subaccounts_count_violation = _level_violation(subaccounts_count, subaccounts_count_levels)
    subaccounts_error_state = api_error_state if subaccounts_error is not None else State.OK
    snapshot_limit_usage_percent = _limit_usage_percent(snapshots_count, snapshot_limit)
    subaccount_limit_usage_percent = _limit_usage_percent(subaccounts_count, subaccounts_limit)
    snapshot_limit_usage_violation = _level_violation(snapshot_limit_usage_percent, snapshot_limit_usage_levels)
    subaccount_limit_usage_violation = _level_violation(subaccount_limit_usage_percent, subaccount_limit_usage_levels)
    snapshot_limit_usage_text = _limit_usage_text(
        "Snapshot limit usage",
        snapshots_count,
        snapshot_limit,
        snapshot_limit_usage_percent,
    )
    subaccount_limit_usage_text = _limit_usage_text(
        "Subaccount limit usage",
        subaccounts_count,
        subaccounts_limit,
        subaccount_limit_usage_percent,
    )
    snapshot_count_state = _violation_state(snapshot_count_violation)
    subaccounts_state = _worst_state(_violation_state(subaccounts_count_violation), subaccounts_error_state)

    status = _string_at(storage_box, ("status",)) or "unknown"
    status_state = State.OK if status.lower() in ACTIVE_STATUSES else _state_from_params(params, "status_state", State.WARN)

    usage_percent = _usage_percent(used_bytes, total_bytes)
    usage_state = _usage_state(usage_percent, usage_levels)
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
        snapshot_limit_usage_text=snapshot_limit_usage_text,
        subaccount_limit_usage_text=subaccount_limit_usage_text,
        snapshot_size_violation=snapshot_size_violation,
        snapshot_count_violation=snapshot_count_violation,
        subaccounts_count_violation=subaccounts_count_violation,
        subaccounts_error_state=subaccounts_error_state,
        api_errors=section["errors"],
        api_error_state=api_error_state,
    )

    for field in fields:
        yield _summary_result(field["state"], field["text"], field["details"])

    yield from _metadata_results(
        storage_box=storage_box,
        params=params,
        snapshots_count=snapshots_count,
        snapshot_limit=snapshot_limit,
        snapshot_limit_usage_text=snapshot_limit_usage_text,
        snapshot_limit_usage_violation=snapshot_limit_usage_violation,
        suppress_ok_snapshot_limit_usage_result=snapshot_count_state != State.OK,
        subaccounts_count=subaccounts_count,
        subaccounts_limit=subaccounts_limit,
        subaccount_limit_usage_text=subaccount_limit_usage_text,
        subaccount_limit_usage_violation=subaccount_limit_usage_violation,
        suppress_ok_subaccount_limit_usage_result=subaccounts_state != State.OK,
    )

    yield from _metrics(
        usage_levels=usage_levels,
        snapshot_size_levels=snapshot_size_levels,
        snapshot_count_levels=snapshot_count_levels,
        subaccounts_count_levels=subaccounts_count_levels,
        snapshot_limit_usage_levels=snapshot_limit_usage_levels,
        subaccount_limit_usage_levels=subaccount_limit_usage_levels,
        used_bytes=used_bytes,
        total_bytes=total_bytes,
        usage_percent=usage_percent,
        data_bytes=data_bytes,
        snapshots_bytes=snapshots_bytes,
        snapshots_count=snapshots_count,
        subaccounts_count=subaccounts_count,
        snapshot_limit=snapshot_limit,
        subaccounts_limit=subaccounts_limit,
        snapshot_limit_usage_percent=snapshot_limit_usage_percent,
        subaccount_limit_usage_percent=subaccount_limit_usage_percent,
    )


def _format_errors(errors: list[ErrorInfo]) -> str:
    summary = _format_error("API error", errors[0])
    if len(errors) > 1:
        summary += f" (+{len(errors) - 1} more)"
    return summary


def _format_error(prefix: str, error: ErrorInfo) -> str:
    return f"{prefix} ({error['code']}): {error['message']}"


def _summary_result(state: State, text: str, details: str | None = None) -> Result:
    details_text = text if details is None else details
    return Result(
        state=state,
        summary=_text_before_state_marker(state, text),
        details=_details_before_state_marker(state, details_text),
    )


def _notice_result(state: State, notice: str, details: str) -> Result:
    return Result(
        state=state,
        notice=_text_before_state_marker(state, notice),
        details=_details_before_state_marker(state, details),
    )


def _text_before_state_marker(state: State, text: str) -> str:
    if state == State.OK:
        return text
    return f"{text.rstrip()} "


def _details_before_state_marker(state: State, details: str) -> str:
    if details == HIDDEN_DETAILS:
        return details
    return _text_before_state_marker(state, details)


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
    snapshot_limit_usage_text: str | None,
    subaccount_limit_usage_text: str | None,
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
        snapshot_count_state = _violation_state(snapshot_count_violation)
        parts.append(
            _display_field(
                "Snapshot count " + _format_count(snapshots_count),
                snapshot_count_state,
                details=_count_details(snapshot_count_state, snapshot_limit_usage_text),
            )
        )
    else:
        parts.append(_display_field("Snapshot count n/a"))

    if subaccounts_count is not None:
        subaccounts_state = _worst_state(_violation_state(subaccounts_count_violation), subaccounts_error_state)
        parts.append(
            _display_field(
                "Subaccounts " + _format_count(subaccounts_count),
                subaccounts_state,
                details=_count_details(subaccounts_state, subaccount_limit_usage_text),
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


def _display_field(text: str, state: State = State.OK, details: str | None = None) -> DisplayField:
    return {"text": text, "details": text if details is None else details, "state": state}


def _count_details(state: State, limit_usage_text: str | None) -> str | None:
    if limit_usage_text is None:
        return None
    return HIDDEN_DETAILS if state == State.OK else limit_usage_text


def _metadata_results(
    *,
    storage_box: Mapping[str, Any],
    params: Mapping[str, Any],
    snapshots_count: float | None,
    snapshot_limit: float | None,
    snapshot_limit_usage_text: str | None,
    snapshot_limit_usage_violation: LevelViolation | None,
    suppress_ok_snapshot_limit_usage_result: bool,
    subaccounts_count: float | None,
    subaccounts_limit: float | None,
    subaccount_limit_usage_text: str | None,
    subaccount_limit_usage_violation: LevelViolation | None,
    suppress_ok_subaccount_limit_usage_result: bool,
) -> Iterable[Result]:
    snapshot_limit_usage_result = _limit_usage_result(
        text=snapshot_limit_usage_text,
        violation=snapshot_limit_usage_violation,
        suppress_ok=suppress_ok_snapshot_limit_usage_result,
    )
    if snapshot_limit_usage_result is not None:
        yield snapshot_limit_usage_result

    subaccount_limit_usage_result = _limit_usage_result(
        text=subaccount_limit_usage_text,
        violation=subaccount_limit_usage_violation,
        suppress_ok=suppress_ok_subaccount_limit_usage_result,
    )
    if subaccount_limit_usage_result is not None:
        yield subaccount_limit_usage_result

    yield _access_result(storage_box, params)
    yield _delete_protection_result(storage_box, params)
    yield _snapshot_plan_result(storage_box, params)


def _access_result(storage_box: Mapping[str, Any], params: Mapping[str, Any]) -> Result:
    access_details = _access_details(storage_box)
    expected_lines = _access_expected_lines(storage_box, params)
    if expected_lines:
        return _notice_result(
            _state_from_params(params, "access_mismatch_state", State.WARN),
            "Access settings mismatch",
            "\n".join((access_details, *expected_lines)),
        )
    return Result(state=State.OK, notice=access_details, details=access_details)


def _access_details(storage_box: Mapping[str, Any]) -> str:
    return "Access: " + ", ".join(
        f"{label} {_format_enabled(_bool_at(storage_box, path))}"
        for _param_key, path, label in ACCESS_SETTINGS
    )


def _access_expected_lines(storage_box: Mapping[str, Any], params: Mapping[str, Any]) -> list[str]:
    expected_lines: list[str] = []
    for param_key, path, label in ACCESS_SETTINGS:
        expected = str(params.get(param_key, "ignore"))
        if expected not in EXPECTED_BOOL_VALUES:
            continue
        actual = _bool_at(storage_box, path)
        if actual is None or actual == EXPECTED_BOOL_VALUES[expected]:
            continue
        expected_lines.append(f"Expected {label}: {expected}")
    return expected_lines


def _delete_protection_result(storage_box: Mapping[str, Any], params: Mapping[str, Any]) -> Result:
    value = _bool_at(storage_box, ("protection", "delete"))
    details = f"Delete protection: {_format_enabled(value)}"
    expected = str(params.get("delete_protection", "ignore"))
    if expected in EXPECTED_BOOL_VALUES and value is not None and value != EXPECTED_BOOL_VALUES[expected]:
        return _notice_result(
            _state_from_params(params, "delete_protection_state", State.WARN),
            "Delete protection mismatch",
            f"{details}\nExpected delete protection: {expected}",
        )
    return Result(state=State.OK, notice=details, details=details)


def _snapshot_plan_result(storage_box: Mapping[str, Any], params: Mapping[str, Any]) -> Result:
    plan_value = _value_at(storage_box, ("snapshot_plan",))
    plan_state = _snapshot_plan_state(plan_value)
    details = f"Snapshot plan: {plan_state}"
    expected = str(params.get("snapshot_plan", "ignore"))
    if expected in ("configured", "none") and plan_state in ("configured", "none") and plan_state != expected:
        return _notice_result(
            _state_from_params(params, "snapshot_plan_state", State.WARN),
            "Snapshot plan mismatch",
            f"{details}\nExpected snapshot plan: {expected}",
        )
    return Result(state=State.OK, notice=details, details=details)


def _snapshot_plan_state(value: Any) -> str:
    if value is MISSING:
        return "n/a"
    return "none" if value is None else "configured"


def _limit_usage_result(
    *,
    text: str | None,
    violation: LevelViolation | None,
    suppress_ok: bool,
) -> Result | None:
    state = _violation_state(violation)
    if text is None or (state == State.OK and suppress_ok):
        return None
    return _notice_result(state, text, text)


def _limit_usage_text(
    label: str,
    count: float | None,
    limit: float | None,
    usage_percent: float | None,
) -> str | None:
    if usage_percent is None or count is None or limit is None:
        return None
    return f"{label}: {_format_count(count)} / {_format_count(limit)} ({usage_percent:.1f}%)"


def _metrics(
    *,
    usage_levels: Levels | None,
    snapshot_size_levels: Levels | None,
    snapshot_count_levels: Levels | None,
    subaccounts_count_levels: Levels | None,
    snapshot_limit_usage_levels: Levels | None,
    subaccount_limit_usage_levels: Levels | None,
    used_bytes: float | None,
    total_bytes: float | None,
    usage_percent: float | None,
    data_bytes: float | None,
    snapshots_bytes: float | None,
    snapshots_count: float | None,
    subaccounts_count: float | None,
    snapshot_limit: float | None,
    subaccounts_limit: float | None,
    snapshot_limit_usage_percent: float | None,
    subaccount_limit_usage_percent: float | None,
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
    if snapshot_limit is not None:
        yield Metric("snapshot_limit", snapshot_limit)
    if subaccounts_limit is not None:
        yield Metric("subaccounts_limit", subaccounts_limit)
    if snapshot_limit_usage_percent is not None:
        yield Metric(
            "snapshot_limit_usage_percent",
            snapshot_limit_usage_percent,
            levels=snapshot_limit_usage_levels,
            boundaries=(0.0, 100.0),
        )
    if subaccount_limit_usage_percent is not None:
        yield Metric(
            "subaccount_limit_usage_percent",
            subaccount_limit_usage_percent,
            levels=subaccount_limit_usage_levels,
            boundaries=(0.0, 100.0),
        )


def _usage_percent(used_bytes: float | None, total_bytes: float | None) -> float | None:
    if used_bytes is None or total_bytes in (None, 0):
        return None
    return used_bytes / total_bytes * 100.0


def _limit_usage_percent(count: float | None, limit: float | None) -> float | None:
    if count is None or limit is None or limit <= 0:
        return None
    return count / limit * 100.0


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
    value = _value_at(data, path)

    if value is MISSING or isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_at(data: Mapping[str, Any], path: tuple[str, ...]) -> str | None:
    value = _value_at(data, path)
    if value is MISSING or value in (None, ""):
        return None
    return str(value)


def _bool_at(data: Mapping[str, Any], path: tuple[str, ...]) -> bool | None:
    value = _value_at(data, path)
    if isinstance(value, bool):
        return value
    return None


def _value_at(data: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = data
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return MISSING
        value = value.get(key)
    return value


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


def _format_enabled(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "enabled" if value else "disabled"


check_plugin_hetzner_storagebox = CheckPlugin(
    name="hetzner_storagebox",
    service_name="Hetzner Storage Box %s",
    discovery_function=discover_hetzner_storagebox,
    check_function=check_hetzner_storagebox,
    check_default_parameters={
        "usage_levels": ("fixed", (80.0, 90.0)),
        "status_state": "WARN",
        "api_error_state": "UNKNOWN",
        "access_mismatch_state": "WARN",
        "delete_protection_state": "WARN",
        "snapshot_plan_state": "WARN",
    },
    check_ruleset_name="hetzner_storagebox",
)
