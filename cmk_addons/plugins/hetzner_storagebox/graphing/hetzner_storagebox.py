#!/usr/bin/env python3
"""Graphing metric definitions for Hetzner Storage Box services."""

from __future__ import annotations

from cmk.graphing.v1 import Title, graphs, metrics

UNIT_BYTES = metrics.Unit(metrics.IECNotation("B"))
UNIT_PERCENT = metrics.Unit(metrics.DecimalNotation("%"))
UNIT_COUNT = metrics.Unit(metrics.DecimalNotation(""))


metric_used_bytes = metrics.Metric(
    name="used_bytes",
    title=Title("Used"),
    unit=UNIT_BYTES,
    color=metrics.Color.BLUE,
)

metric_total_bytes = metrics.Metric(
    name="total_bytes",
    title=Title("Total"),
    unit=UNIT_BYTES,
    color=metrics.Color.DARK_BLUE,
)

metric_used_percent = metrics.Metric(
    name="used_percent",
    title=Title("Used %"),
    unit=UNIT_PERCENT,
    color=metrics.Color.GREEN,
)

metric_data_bytes = metrics.Metric(
    name="data_bytes",
    title=Title("Data"),
    unit=UNIT_BYTES,
    color=metrics.Color.CYAN,
)

metric_snapshots_bytes = metrics.Metric(
    name="snapshots_bytes",
    title=Title("Snapshots"),
    unit=UNIT_BYTES,
    color=metrics.Color.PURPLE,
)

metric_snapshots_count = metrics.Metric(
    name="snapshots_count",
    title=Title("Snapshot count"),
    unit=UNIT_COUNT,
    color=metrics.Color.DARK_PURPLE,
)

metric_subaccounts_count = metrics.Metric(
    name="subaccounts_count",
    title=Title("Subaccount count"),
    unit=UNIT_COUNT,
    color=metrics.Color.ORANGE,
)

metric_snapshot_limit = metrics.Metric(
    name="snapshot_limit",
    title=Title("Snapshot limit"),
    unit=UNIT_COUNT,
    color=metrics.Color.LIGHT_PURPLE,
)

metric_subaccounts_limit = metrics.Metric(
    name="subaccounts_limit",
    title=Title("Subaccount limit"),
    unit=UNIT_COUNT,
    color=metrics.Color.LIGHT_ORANGE,
)

metric_snapshot_limit_usage_percent = metrics.Metric(
    name="snapshot_limit_usage_percent",
    title=Title("Snapshot limit usage"),
    unit=UNIT_PERCENT,
    color=metrics.Color.DARK_PURPLE,
)

metric_subaccount_limit_usage_percent = metrics.Metric(
    name="subaccount_limit_usage_percent",
    title=Title("Subaccount limit usage"),
    unit=UNIT_PERCENT,
    color=metrics.Color.DARK_ORANGE,
)


graph_hetzner_storagebox_storage_usage = graphs.Graph(
    name="hetzner_storagebox_storage_usage",
    title=Title("Storage usage"),
    simple_lines=(
        "used_bytes",
        "data_bytes",
        "snapshots_bytes",
        "total_bytes",
    ),
    optional=(
        "data_bytes",
        "snapshots_bytes",
    ),
)

graph_hetzner_storagebox_used_percent = graphs.Graph(
    name="hetzner_storagebox_used_percent",
    title=Title("Storage usage percentage"),
    minimal_range=graphs.MinimalRange(0, 100),
    simple_lines=(
        "used_percent",
        metrics.WarningOf("used_percent"),
        metrics.CriticalOf("used_percent"),
    ),
)

graph_hetzner_storagebox_counts = graphs.Graph(
    name="hetzner_storagebox_counts",
    title=Title("Storage Box counts"),
    simple_lines=(
        "snapshots_count",
        "snapshot_limit",
        "subaccounts_count",
        "subaccounts_limit",
    ),
    optional=(
        "snapshots_count",
        "snapshot_limit",
        "subaccounts_count",
        "subaccounts_limit",
    ),
)

graph_hetzner_storagebox_limit_usage_percent = graphs.Graph(
    name="hetzner_storagebox_limit_usage_percent",
    title=Title("Storage Box limit usage percentage"),
    minimal_range=graphs.MinimalRange(0, 100),
    simple_lines=(
        "snapshot_limit_usage_percent",
        metrics.WarningOf("snapshot_limit_usage_percent"),
        metrics.CriticalOf("snapshot_limit_usage_percent"),
        "subaccount_limit_usage_percent",
        metrics.WarningOf("subaccount_limit_usage_percent"),
        metrics.CriticalOf("subaccount_limit_usage_percent"),
    ),
    optional=(
        "snapshot_limit_usage_percent",
        "subaccount_limit_usage_percent",
    ),
)
