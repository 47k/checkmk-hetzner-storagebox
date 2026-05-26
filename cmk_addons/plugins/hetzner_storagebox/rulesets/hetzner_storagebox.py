from cmk.rulesets.v1 import Label, Title, Topic
from cmk.rulesets.v1.form_specs import BooleanChoice, DefaultValue, DictElement, Dictionary, Integer, Password, String
from cmk.rulesets.v1.rule_specs import CheckParameters, HostCondition, SpecialAgent


def _special_agent_parameter_form() -> Dictionary:
    return Dictionary(
        title=Title("hetzner_storagebox"),
        elements={
            "url": DictElement(required=True, parameter_form=String(title=Title("URL"))),
            "username": DictElement(required=True, parameter_form=String(title=Title("Username"))),
            "password": DictElement(required=True, parameter_form=Password(title=Title("Password"))),
            "timeout": DictElement(required=False, parameter_form=Integer(title=Title("Timeout (seconds)"))),
            "insecure": DictElement(
                required=True,
                parameter_form=BooleanChoice(
                    label=Label("Disable TLS certificate verification"),
                    prefill=DefaultValue(False),
                ),
            ),
        },
    )


def _check_parameter_form() -> Dictionary:
    return Dictionary(
        elements={
            "warn": DictElement(required=False, parameter_form=Integer(title=Title("Warning if value is at least"))),
            "crit": DictElement(required=False, parameter_form=Integer(title=Title("Critical if value is at least"))),
        },
    )


rule_spec_hetzner_storagebox = SpecialAgent(
    name="hetzner_storagebox",
    title=Title("hetzner_storagebox"),
    topic=Topic.APPLICATIONS,
    parameter_form=_special_agent_parameter_form,
)


rule_spec_check_parameters_hetzner_storagebox = CheckParameters(
    name="hetzner_storagebox",
    title=Title("hetzner_storagebox"),
    topic=Topic.APPLICATIONS,
    parameter_form=_check_parameter_form,
    condition=HostCondition(),
)
