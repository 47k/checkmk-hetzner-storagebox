from cmk.agent_based.v2 import AgentSection, CheckPlugin, Metric, Result, Service, State


def parse_hetzner_storagebox(string_table):
    if not string_table:
        return None

    # Expected format from special agent: status|value
    raw = " ".join(string_table[0])
    parts = raw.split("|", 1)
    if len(parts) != 2:
        return None

    return {"status": parts[0], "value": parts[1]}


agent_section_hetzner_storagebox = AgentSection(
    name="hetzner_storagebox",
    parse_function=parse_hetzner_storagebox,
)


def discover_hetzner_storagebox(section):
    if section:
        yield Service()


def check_hetzner_storagebox(params, section):
    if not section:
        yield Result(state=State.CRIT, summary="No data received")
        return

    warn = params.get("warn", 80)
    crit = params.get("crit", 90)

    try:
        value = float(section["value"])
    except Exception:
        yield Result(state=State.CRIT, summary=f"Invalid value: {section['value']}")
        return

    if value >= crit:
        state = State.CRIT
    elif value >= warn:
        state = State.WARN
    else:
        state = State.OK

    yield Result(state=state, summary=f"Current value: {value}")
    yield Metric("value", value)


check_plugin_hetzner_storagebox = CheckPlugin(
    name="hetzner_storagebox",
    service_name="hetzner_storagebox",
    discovery_function=discover_hetzner_storagebox,
    check_function=check_hetzner_storagebox,
    check_default_parameters={"warn": 80, "crit": 90},
    check_ruleset_name="hetzner_storagebox",
)
