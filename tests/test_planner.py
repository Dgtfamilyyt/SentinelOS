from ai.planner import Planner
from tools.manager import ToolManager


def build_planner():

    tools = ToolManager()
    tools.discover()

    return Planner(tools)


def test_fast_list_files():

    planner = build_planner()

    plan = planner.plan(
        "list files"
    )

    assert plan["type"] == "tool"
    assert plan["tool"] == "list_files"

    assert plan["parameters"] == {}


def test_fast_read_file():

    planner = build_planner()

    plan = planner.plan(
        "read hello.txt"
    )

    assert plan == {
        "type": "tool",
        "task": "chat",
        "tool": "read_file",
        "parameters": {
            "filename": "hello.txt"
        },
    }


def test_parse_red_mode():

    planner = build_planner()

    raw = """
    {
        "type": "chat",
        "task": "red"
    }
    """

    plan = planner._parse(
        raw,
        "red team enumeration"
    )

    assert plan["type"] == "chat"
    assert plan["task"] == "red"


def test_reject_fake_tool():

    planner = build_planner()

    raw = """
    {
        "type": "tool",
        "task": "red",
        "tool": "hack_the_planet",
        "parameters": {}
    }
    """

    plan = planner._parse(
        raw,
        "do something"
    )

    assert plan == {
        "type": "chat",
        "task": "red"
    }


def test_invalid_json_fallback():

    planner = build_planner()

    plan = planner._parse(
        "not json",
        "analyze this SOC alert"
    )

    assert plan["type"] == "chat"
    assert plan["task"] == "soc"