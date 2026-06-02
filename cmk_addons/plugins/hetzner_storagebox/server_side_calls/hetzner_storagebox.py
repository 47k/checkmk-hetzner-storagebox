#!/usr/bin/env python3
"""Server-side call configuration for the Hetzner Storage Box special agent."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from cmk.server_side_calls.v1 import Secret, SpecialAgentCommand, SpecialAgentConfig, noop_parser

DEFAULT_API_URL = "https://api.hetzner.com/v1"
DEFAULT_CACHE_TTL_SECONDS = 3600


def _split_box_ids(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]

    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        box_ids: list[str] = []
        for item in value:
            box_ids.extend(_split_box_ids(item))
        return box_ids

    normalized = str(value).strip()
    return [normalized] if normalized else []


def _first_present(params: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in params and params[key] is not None:
            return params[key]
    return None


def _bool_param(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
    return bool(value)


def _int_param(value: Any, default: int) -> int:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(float(value.strip())))
        except ValueError:
            return default
    return default


def _cache_arguments(params: Mapping[str, Any]) -> tuple[bool, int, bool]:
    raw_cache = _first_present(params, ("cache_enabled", "cache", "result_cache"))
    ttl_value = _first_present(params, ("cache_ttl",))
    stale_on_error_value = _first_present(params, ("cache_stale_on_error", "stale_on_error"))

    if isinstance(raw_cache, tuple) and len(raw_cache) == 2:
        choice, nested_value = raw_cache
        cache_enabled = _bool_param(choice, True)
        if isinstance(nested_value, Mapping):
            nested_ttl = _first_present(nested_value, ("cache_ttl", "ttl"))
            if nested_ttl is not None:
                ttl_value = nested_ttl
            nested_stale_on_error = _first_present(nested_value, ("cache_stale_on_error", "stale_on_error"))
            if nested_stale_on_error is not None:
                stale_on_error_value = nested_stale_on_error
    elif isinstance(raw_cache, Mapping):
        cache_enabled = _bool_param(_first_present(raw_cache, ("enabled", "cache_enabled")), True)
        nested_ttl = _first_present(raw_cache, ("cache_ttl", "ttl"))
        if nested_ttl is not None:
            ttl_value = nested_ttl
        nested_stale_on_error = _first_present(raw_cache, ("cache_stale_on_error", "stale_on_error"))
        if nested_stale_on_error is not None:
            stale_on_error_value = nested_stale_on_error
    else:
        cache_enabled = _bool_param(raw_cache, True)

    return (
        cache_enabled,
        _int_param(ttl_value, DEFAULT_CACHE_TTL_SECONDS),
        _bool_param(stale_on_error_value, True),
    )


def _agent_arguments(params: Mapping[str, Any], _host_config: Any) -> Iterable[SpecialAgentCommand]:
    api_token = params["api_token"]
    api_url = str(params.get("api_url") or DEFAULT_API_URL)
    timeout = int(params.get("timeout") or 10)

    arguments: list[str | Secret] = [
        "--api-token",
        api_token,
        "--api-url",
        api_url,
        "--timeout",
        str(timeout),
    ]

    for box_id in _split_box_ids(params.get("box_ids")):
        arguments.extend(["--box-id", box_id])

    arguments.append("--fetch-subaccounts")

    cache_enabled, cache_ttl, cache_stale_on_error = _cache_arguments(params)
    arguments.append("--cache-enabled" if cache_enabled else "--no-cache-enabled")
    arguments.extend(["--cache-ttl", str(cache_ttl)])
    arguments.append("--cache-stale-on-error" if cache_stale_on_error else "--no-cache-stale-on-error")

    yield SpecialAgentCommand(command_arguments=arguments)


special_agent_hetzner_storagebox = SpecialAgentConfig(
    name="hetzner_storagebox",
    parameter_parser=noop_parser,
    commands_function=_agent_arguments,
)
