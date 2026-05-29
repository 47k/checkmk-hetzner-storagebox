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
    "<tt>stats.size / storage_box_type.size</tt>. When this option is unchecked, "
    "the effective default levels are WARN at 80% and CRIT at 90%. This is useful "
    "for capacity planning."
)
HELP_SNAPSHOT_SIZE_LEVELS = Help(
    "Monitors the space used by snapshots based on <tt>stats.size_snapshots</tt>. "
    "The levels are only evaluated when the API provides this value. Leave this option "
    "unchecked to disable alerting for snapshot size."
)
HELP_SNAPSHOT_COUNT_LEVELS = Help(
    "Monitors the number of snapshots based on <tt>snapshots_count</tt>, if available. "
    "If the API does not provide this field, the check shows <i>Snapshot count n/a</i> "
    "and does not alert. Leave this option unchecked to disable alerting for snapshot "
    "count. This value is not inferred from <tt>snapshot_limit</tt>."
)
HELP_SUBACCOUNT_COUNT_LEVELS = Help(
    "Monitors the number of configured Storage Box subaccounts. The count is fetched "
    "from the Storage Box subaccounts API. If the subaccount endpoint cannot be "
    "queried, the count remains unavailable and the check reports the API subaccount "
    "error separately. Leave this option unchecked to disable alerting for subaccount "
    "count. This can help detect unexpected growth or account sprawl."
)
HELP_ACCESS_EXPECTATION = Help(
    "Optionally checks the corresponding value from <tt>access_settings</tt>. Leave this option "
    "unchecked unless the access setting should be enforced. Missing API fields are shown as "
    "<tt>n/a</tt> and do not alert."
)
HELP_ACCESS_MISMATCH_STATE = Help(
    "Controls the service state when one or more configured access settings differ from the "
    "expected value. The default is WARN."
)
HELP_DELETE_PROTECTION = Help(
    "Optionally checks <tt>protection.delete</tt>. Leave this option unchecked unless delete "
    "protection should be enforced. Missing API fields are shown as <tt>n/a</tt> and do not alert."
)
HELP_DELETE_PROTECTION_STATE = Help(
    "Controls the service state when the configured delete protection expectation is not met. "
    "The default is WARN."
)
HELP_SNAPSHOT_PLAN = Help(
    "Optionally checks whether <tt>snapshot_plan</tt> is configured. A value of <tt>null</tt> means "
    "no snapshot plan. Any non-null value means a plan is configured. Leave this option unchecked "
    "to ignore the snapshot plan. Missing API fields are shown as <tt>n/a</tt> and do not alert."
)
HELP_SNAPSHOT_PLAN_STATE = Help(
    "Controls the service state when the configured snapshot plan requirement is not met. "
    "The default is WARN."
)
HELP_SNAPSHOT_LIMIT_USAGE = Help(
    "Monitors <tt>snapshots_count</tt> as a percentage of <tt>storage_box_type.snapshot_limit</tt>. "
    "The levels are only evaluated when both values are available and the limit is greater than "
    "zero. Leave this option unchecked to disable alerting."
)
HELP_SUBACCOUNT_LIMIT_USAGE = Help(
    "Monitors <tt>subaccounts_count</tt> as a percentage of "
    "<tt>storage_box_type.subaccounts_limit</tt>. The levels are only evaluated when both values "
    "are available and the limit is greater than zero. Leave this option unchecked to disable alerting."
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


def _expected_access_choice(title: Title, help_text: Help) -> SingleChoice:
    return SingleChoice(
        title=title,
        help_text=help_text,
        prefill=DefaultValue("enabled"),
        elements=(
            SingleChoiceElement("enabled", Title("Expected enabled")),
            SingleChoiceElement("disabled", Title("Expected disabled")),
        ),
        ignored_elements=("ignore",),
    )


def _delete_protection_choice() -> SingleChoice:
    return SingleChoice(
        title=Title("Delete protection"),
        help_text=HELP_DELETE_PROTECTION,
        prefill=DefaultValue("enabled"),
        elements=(
            SingleChoiceElement("enabled", Title("Expected enabled")),
            SingleChoiceElement("disabled", Title("Expected disabled")),
        ),
        ignored_elements=("ignore",),
    )


def _snapshot_plan_choice() -> SingleChoice:
    return SingleChoice(
        title=Title("Snapshot plan"),
        help_text=HELP_SNAPSHOT_PLAN,
        prefill=DefaultValue("configured"),
        elements=(
            SingleChoiceElement("configured", Title("Require configured snapshot plan")),
            SingleChoiceElement("none", Title("Require no snapshot plan")),
        ),
        ignored_elements=("ignore",),
    )


def _check_parameter_form() -> Dictionary:
    return Dictionary(
        title=Title("Hetzner Storage Box service parameters"),
        help_text=Help(
            "<b>Configure Hetzner Storage Box service monitoring</b><br>"
            "This rule controls how Hetzner Storage Box services are evaluated after data has been collected "
            "from the Hetzner Console API.<br>"
            "<br>"
            "<b>Default monitoring</b>"
            "<ul>"
            "<li>Storage usage based on <tt>stats.size</tt> and the Storage Box capacity.</li>"
            "<li>Non-active Storage Box status handling.</li>"
            "<li>API collection, authentication, and network error handling.</li>"
            "</ul>"
            "<b>Optional monitoring</b>"
            "<ul>"
            "<li>Snapshot size and snapshot count monitoring.</li>"
            "<li>Subaccount count monitoring.</li>"
            "<li>Access setting validation for Samba, SSH, WebDAV, ZFS, and external reachability.</li>"
            "<li>Delete protection monitoring.</li>"
            "<li>Snapshot plan monitoring.</li>"
            "<li>Snapshot and subaccount limit usage monitoring.</li>"
            "</ul>"
            "<b>Default behavior</b>"
            "<ul>"
            "<li>Storage usage uses WARN at 80% and CRIT at 90% unless overridden.</li>"
            "<li>Snapshot, subaccount, access-setting, delete-protection, snapshot-plan, and limit-usage "
            "checks are disabled or ignored unless explicitly enabled.</li>"
            "<li>Non-active Storage Box status defaults to WARN.</li>"
            "<li>API collection errors default to UNKNOWN.</li>"
            "</ul>"
            "<b>Unavailable API fields</b>"
            "<ul>"
            "<li>If Hetzner does not provide an optional field, the service shows <tt>n/a</tt> and does not "
            "alert for the missing value.</li>"
            "<li>Missing optional values never trigger alerts by themselves.</li>"
            "</ul>"
            "<b>Severity handling</b><br>"
            "Severity options are checkbox-enabled overrides. When they are not configured, the plugin uses "
            "the effective defaults listed above."
            "<br>"
        ),
        elements={
            "usage_levels": DictElement(
                required=False,
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
                required=False,
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
                required=False,
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
                required=False,
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
            "expected_samba_access": DictElement(
                required=False,
                parameter_form=_expected_access_choice(Title("Expected Samba access"), HELP_ACCESS_EXPECTATION),
            ),
            "expected_ssh_access": DictElement(
                required=False,
                parameter_form=_expected_access_choice(Title("Expected SSH access"), HELP_ACCESS_EXPECTATION),
            ),
            "expected_webdav_access": DictElement(
                required=False,
                parameter_form=_expected_access_choice(Title("Expected WebDAV access"), HELP_ACCESS_EXPECTATION),
            ),
            "expected_zfs_access": DictElement(
                required=False,
                parameter_form=_expected_access_choice(Title("Expected ZFS access"), HELP_ACCESS_EXPECTATION),
            ),
            "expected_external_reachability": DictElement(
                required=False,
                parameter_form=_expected_access_choice(
                    Title("Expected external reachability"),
                    HELP_ACCESS_EXPECTATION,
                ),
            ),
            "access_mismatch_state": DictElement(
                required=False,
                parameter_form=_severity_choice(
                    Title("Severity for access setting mismatches"),
                    "WARN",
                    help_text=HELP_ACCESS_MISMATCH_STATE,
                    allow_ok=False,
                ),
            ),
            "delete_protection": DictElement(
                required=False,
                parameter_form=_delete_protection_choice(),
            ),
            "delete_protection_state": DictElement(
                required=False,
                parameter_form=_severity_choice(
                    Title("Severity for delete protection mismatch"),
                    "WARN",
                    help_text=HELP_DELETE_PROTECTION_STATE,
                    allow_ok=False,
                ),
            ),
            "snapshot_plan": DictElement(
                required=False,
                parameter_form=_snapshot_plan_choice(),
            ),
            "snapshot_plan_state": DictElement(
                required=False,
                parameter_form=_severity_choice(
                    Title("Severity for snapshot plan mismatch"),
                    "WARN",
                    help_text=HELP_SNAPSHOT_PLAN_STATE,
                    allow_ok=False,
                ),
            ),
            "snapshot_limit_usage_levels": DictElement(
                required=False,
                parameter_form=SimpleLevels[float](
                    title=Title("Snapshot limit usage"),
                    help_text=HELP_SNAPSHOT_LIMIT_USAGE,
                    form_spec_template=Float(
                        help_text=HELP_SNAPSHOT_LIMIT_USAGE,
                        unit_symbol="%",
                        custom_validate=(validators.NumberInRange(min_value=0.0, max_value=100.0),),
                    ),
                    level_direction=LevelDirection.UPPER,
                    prefill_levels_type=DefaultValue(LevelsType.NONE),
                    prefill_fixed_levels=InputHint(value=(0.0, 0.0)),
                ),
            ),
            "subaccount_limit_usage_levels": DictElement(
                required=False,
                parameter_form=SimpleLevels[float](
                    title=Title("Subaccount limit usage"),
                    help_text=HELP_SUBACCOUNT_LIMIT_USAGE,
                    form_spec_template=Float(
                        help_text=HELP_SUBACCOUNT_LIMIT_USAGE,
                        unit_symbol="%",
                        custom_validate=(validators.NumberInRange(min_value=0.0, max_value=100.0),),
                    ),
                    level_direction=LevelDirection.UPPER,
                    prefill_levels_type=DefaultValue(LevelsType.NONE),
                    prefill_fixed_levels=InputHint(value=(0.0, 0.0)),
                ),
            ),
            "status_state": DictElement(
                required=False,
                parameter_form=_severity_choice(
                    Title("Severity for non-active Storage Box status"),
                    "WARN",
                    help_text=HELP_STATUS_STATE,
                ),
            ),
            "api_error_state": DictElement(
                required=False,
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
