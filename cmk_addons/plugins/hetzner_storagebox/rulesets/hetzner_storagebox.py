#!/usr/bin/env python3
"""Rulesets for Hetzner Storage Box monitoring."""

from __future__ import annotations

from cmk.rulesets.v1 import Help, Label, Title
from cmk.rulesets.v1.form_specs import (
    DataSize,
    DefaultValue,
    DictElement,
    Dictionary,
    Float,
    IECMagnitude,
    InputHint,
    Integer,
    LevelDirection,
    LevelsType,
    List,
    Password,
    SimpleLevels,
    SingleChoice,
    SingleChoiceElement,
    String,
    migrate_to_password,
    validators,
)
from cmk.rulesets.v1.rule_specs import CheckParameters, HostAndItemCondition, SpecialAgent, Topic

DEFAULT_API_URL = "https://api.hetzner.com/v1"

HELP_STORAGE_USAGE_LEVELS = Help(
    "Monitors the used Storage Box capacity in percent. The value is calculated from "
    "<tt>stats.size / storage_box_type.size</tt>. The default levels are WARN at 80% "
    "and CRIT at 90%. This is useful for capacity planning."
)
HELP_SNAPSHOT_SIZE_LEVELS = Help(
    "Monitors the space used by snapshots based on <tt>stats.size_snapshots</tt>. "
    "The levels are only evaluated when the API provides this value. Leave this "
    "option unset to disable alerting for snapshot size."
)
HELP_SNAPSHOT_COUNT_LEVELS = Help(
    "Monitors the number of snapshots based on <tt>snapshots_count</tt>, if available. "
    "If the API does not provide this field, the check shows <i>Snapshot count n/a</i> "
    "and does not alert. This value is not inferred from <tt>snapshot_limit</tt>."
)
HELP_SUBACCOUNT_COUNT_LEVELS = Help(
    "Monitors the number of configured Storage Box subaccounts. The count is fetched "
    "from the Storage Box subaccounts API. If the subaccount endpoint cannot be "
    "queried, the count remains unavailable and the check reports the API subaccount "
    "error separately. This can help detect unexpected growth or account sprawl."
)
HELP_STATUS_STATE = Help(
    "Controls the service state when the Storage Box status is not active. The API "
    "status itself is shown as <tt>Status: &lt;value&gt;</tt>. The default is WARN."
)
HELP_API_ERROR_STATE = Help(
    "Controls the service state for API, authentication, or network errors when "
    "Storage Box data cannot be collected. The default is UNKNOWN because the "
    "Storage Box state is unknown, not necessarily broken. Select WARN or CRIT "
    "for stricter alerting."
)


def _special_agent_parameter_form() -> Dictionary:
    return Dictionary(
        title=Title("Hetzner Storage Box"),
        help_text=Help(
            "Configure access to the Hetzner Console API for Storage Box monitoring. "
            "Use a Console API token and the API base URL https://api.hetzner.com/v1."
        ),
        elements={
            "api_token": DictElement(
                required=True,
                parameter_form=Password(
                    title=Title("API token"),
                    help_text=Help("Bearer token for the Hetzner Console API."),
                    migrate=migrate_to_password,
                ),
            ),
            "api_url": DictElement(
                required=False,
                parameter_form=String(
                    title=Title("API base URL"),
                    help_text=Help("Override only when using a compatible Hetzner Console API endpoint."),
                    prefill=DefaultValue(DEFAULT_API_URL),
                    custom_validate=(
                        validators.Url(protocols=(validators.UrlProtocol.HTTP, validators.UrlProtocol.HTTPS)),
                    ),
                ),
            ),
            "timeout": DictElement(
                required=False,
                parameter_form=Integer(
                    title=Title("API timeout"),
                    unit_symbol="s",
                    prefill=DefaultValue(10),
                    custom_validate=(validators.NumberInRange(min_value=1),),
                ),
            ),
            "box_ids": DictElement(
                required=False,
                parameter_form=List(
                    title=Title("Storage Box IDs"),
                    help_text=Help("Optional allow-list of Storage Box IDs to monitor."),
                    element_template=String(title=Title("Storage Box ID")),
                    add_element_label=Label("Add Storage Box ID"),
                    remove_element_label=Label("Remove"),
                ),
            ),
        },
    )


def _severity_choice(
    title: Title,
    default: str,
    help_text: Help | None = None,
    *,
    allow_ok: bool = True,
) -> SingleChoice:
    elements = (
        (
            SingleChoiceElement("OK", Title("OK")),
            SingleChoiceElement("WARN", Title("WARN")),
            SingleChoiceElement("CRIT", Title("CRIT")),
            SingleChoiceElement("UNKNOWN", Title("UNKNOWN")),
        )
        if allow_ok
        else (
            SingleChoiceElement("UNKNOWN", Title("UNKNOWN")),
            SingleChoiceElement("WARN", Title("WARN")),
            SingleChoiceElement("CRIT", Title("CRIT")),
        )
    )
    return SingleChoice(
        title=title,
        help_text=help_text,
        prefill=DefaultValue(default),
        elements=elements,
    )


def _check_parameter_form() -> Dictionary:
    return Dictionary(
        title=Title("Hetzner Storage Box service parameters"),
        help_text=Help(
            "<b>Configure Hetzner Storage Box service monitoring</b><br>"
            "This rule controls how Storage Box services are evaluated after the special agent has collected "
            "data from the Hetzner Console API.<br>"
            "<br>"
            "It defines:"
            "<ul>"
            "<li>Storage usage monitoring based on <tt>stats.size / storage_box_type.size</tt>.</li>"
            "<li>Snapshot monitoring for snapshot size (<tt>stats.size_snapshots</tt>) and snapshot count "
            "(<tt>snapshots_count</tt>).</li>"
            "<li>Subaccount monitoring based on <tt>subaccounts_count</tt>.</li>"
            "<li>Severity handling for non-active Storage Box status values and API, authentication, or "
            "network collection errors.</li>"
            "</ul>"
            "Thresholds are state-neutral unless configured. Storage usage uses the default WARN and CRIT "
            "thresholds unless changed or disabled; snapshot and subaccount thresholds only alert when fixed "
            "thresholds are configured.<br>"
            "<br>"
            "If the API does not provide an optional field, the service shows it as <tt>n/a</tt> and does not "
            "alert for that missing value. API or status problems are handled separately by the configured "
            "severity settings."
        ),
        elements={
            "usage_levels": DictElement(
                required=True,
                parameter_form=SimpleLevels(
                    title=Title("Storage usage"),
                    help_text=HELP_STORAGE_USAGE_LEVELS,
                    form_spec_template=Float(
                        help_text=HELP_STORAGE_USAGE_LEVELS,
                        unit_symbol="%",
                        custom_validate=(validators.NumberInRange(min_value=0.0, max_value=100.0),),
                    ),
                    level_direction=LevelDirection.UPPER,
                    prefill_fixed_levels=DefaultValue((80.0, 90.0)),
                ),
            ),
            "snapshot_size_levels": DictElement(
                required=True,
                parameter_form=SimpleLevels[int](
                    title=Title("Snapshot size"),
                    help_text=HELP_SNAPSHOT_SIZE_LEVELS,
                    form_spec_template=DataSize(
                        help_text=HELP_SNAPSHOT_SIZE_LEVELS,
                        displayed_magnitudes=[
                            IECMagnitude.TEBI,
                            IECMagnitude.GIBI,
                            IECMagnitude.MEBI,
                            IECMagnitude.KIBI,
                            IECMagnitude.BYTE,
                        ],
                    ),
                    level_direction=LevelDirection.UPPER,
                    prefill_levels_type=DefaultValue(LevelsType.NONE),
                    prefill_fixed_levels=InputHint(value=(0, 0)),
                ),
            ),
            "snapshot_count_levels": DictElement(
                required=True,
                parameter_form=SimpleLevels[int](
                    title=Title("Snapshot count"),
                    help_text=HELP_SNAPSHOT_COUNT_LEVELS,
                    form_spec_template=Integer(
                        help_text=HELP_SNAPSHOT_COUNT_LEVELS,
                        unit_symbol="snapshots",
                        custom_validate=(validators.NumberInRange(min_value=0),),
                    ),
                    level_direction=LevelDirection.UPPER,
                    prefill_levels_type=DefaultValue(LevelsType.NONE),
                    prefill_fixed_levels=InputHint(value=(0, 0)),
                ),
            ),
            "subaccounts_count_levels": DictElement(
                required=True,
                parameter_form=SimpleLevels[int](
                    title=Title("Subaccount count"),
                    help_text=HELP_SUBACCOUNT_COUNT_LEVELS,
                    form_spec_template=Integer(
                        help_text=HELP_SUBACCOUNT_COUNT_LEVELS,
                        unit_symbol="subaccounts",
                        custom_validate=(validators.NumberInRange(min_value=0),),
                    ),
                    level_direction=LevelDirection.UPPER,
                    prefill_levels_type=DefaultValue(LevelsType.NONE),
                    prefill_fixed_levels=InputHint(value=(0, 0)),
                ),
            ),
            "status_state": DictElement(
                required=True,
                parameter_form=_severity_choice(
                    Title("Severity for non-active Storage Box status"),
                    "WARN",
                    help_text=HELP_STATUS_STATE,
                ),
            ),
            "api_error_state": DictElement(
                required=True,
                parameter_form=_severity_choice(
                    Title("Severity for API collection errors"),
                    "UNKNOWN",
                    help_text=HELP_API_ERROR_STATE,
                    allow_ok=False,
                ),
            ),
        },
    )


rule_spec_hetzner_storagebox = SpecialAgent(
    name="hetzner_storagebox",
    title=Title("Hetzner Storage Box"),
    topic=Topic.APPLICATIONS,
    parameter_form=_special_agent_parameter_form,
)


rule_spec_check_parameters_hetzner_storagebox = CheckParameters(
    name="hetzner_storagebox",
    title=Title("Hetzner Storage Box"),
    topic=Topic.APPLICATIONS,
    parameter_form=_check_parameter_form,
    condition=HostAndItemCondition(item_title=Title("Storage Box")),
)
