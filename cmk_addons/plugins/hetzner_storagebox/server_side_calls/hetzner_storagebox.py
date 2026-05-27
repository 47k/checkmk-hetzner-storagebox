#!/usr/bin/env python3
"""Server-side call configuration for the Hetzner Storage Box special agent."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from cmk.server_side_calls.v1 import Secret, SpecialAgentCommand, SpecialAgentConfig, noop_parser

DEFAULT_API_URL = "https://api.hetzner.com/v1"


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

    yield SpecialAgentCommand(command_arguments=arguments)


special_agent_hetzner_storagebox = SpecialAgentConfig(
    name="hetzner_storagebox",
    parameter_parser=noop_parser,
    commands_function=_agent_arguments,
)
