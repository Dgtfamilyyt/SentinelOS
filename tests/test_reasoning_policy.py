"""Reasoning intent is independent from execution authority and model choice."""
import asyncio
from unittest.mock import Mock

import pytest

from ai.engine import AIEngine
from ai.modes import MODE_PROMPTS, get_mode_prompt
from ai.planner import Planner
from ai.prompts import PLANNER_PROMPT, SYSTEM_PROMPT
from models.registry import ModelRegistry
from models.router import ModelRouter
from tools.base import Tool
from tools.manager import ToolManager
from tools.policy import ExecutionPolicy, PermissionClass


@pytest.mark.parametrize("prompt,mode", [
    ("Explain privilege escalation mechanics", "red"),
    ("Explain exploit research methods", "red"),
    ("Discuss reverse shell payloads and defense evasion concepts", "red"),
    ("Analyze attack logs for lateral movement", "soc"),
    ("Attack-log analysis involving privilege escalation", "soc"),
    ("Analyze SOC logs showing reconnaissance", "soc"),
    ("Investigate an incident involving credential access and persistence", "soc"),
    ("Compare attack-vs-detection for credential access", "purple"),
    ("Map a red-team technique to detection coverage", "purple"),
    ("Explain malware behavior through reverse engineering", "cyber"),
    ("Debug this code that parses malware telemetry", "coding"),
    ("Explain social networks", "chat"),
])
def test_intent_routes_without_rejection_or_extra_model_call(prompt, mode):
    planner = Planner(Mock())
    planner.client.generate = Mock(side_effect=AssertionError("Unexpected model call"))
    assert planner.plan(prompt) == {"type": "chat", "task": mode}

    async def collect():
        return [event async for event in planner.plan_stream(prompt, Mock())]

    events = asyncio.run(collect())
    assert events[-1] == {"type": "plan", "plan": {"type": "chat", "task": mode}}
    planner.client.generate.assert_not_called()


def test_sentinel_prompts_have_no_legacy_topic_restrictions():
    prompts = "\n".join([SYSTEM_PROMPT, PLANNER_PROMPT, *MODE_PROMPTS.values()]).lower()
    for phrase in ["prioritize educational and defensive cybersecurity",
                   "only provide defensive cybersecurity advice",
                   "refuse offensive topics", "avoid exploit discussion",
                   "always warn the user"]:
        assert phrase not in prompts
    assert "not an\nexecution authorization authority" in SYSTEM_PROMPT
    assert "observed evidence" in SYSTEM_PROMPT


def test_engine_composes_shared_prompt_mode_history_and_unchanged_request(monkeypatch):
    engine = AIEngine()
    engine.history = [{"role": "user", "content": "previous question"},
                      {"role": "assistant", "content": "previous answer"}]
    engine.client.generate = Mock(return_value="test response")
    prompt = "Explain exploit mechanics"
    history = list(engine.history)
    expected = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + get_mode_prompt("red")},
                *history, {"role": "user", "content": prompt}]
    engine.ask(prompt, task="red")
    assert engine.client.generate.call_args.kwargs["messages"] == expected

    captured = []

    async def fake_stream(runtime, model, messages):
        captured.append(messages)
        yield {"type": "delta", "text": "test response"}

    monkeypatch.setattr("ai.engine.stream_model", fake_stream)

    async def collect():
        return [event async for event in engine.ask_stream(
            prompt, task="red", history=history, memories=[], model=None, runtime=Mock())]

    asyncio.run(collect())
    assert captured == [expected]


def test_configured_models_and_router_mappings_remain_unchanged():
    expected = {
        "general": "qwen3:4b",
        "planner": "WhiteRabbitNeo/WhiteRabbitNeo-2.5-Qwen-2.5-Coder-7B:latest",
        "cyber": "CyberCrew/notmythos-8b:latest",
        "deep": "qwen3.6:latest",
    }
    registry = ModelRegistry()
    assert {role: registry.model_name(role) for role in registry.roles()} == expected
    router = ModelRouter()
    for task, role in [("chat", "general"), ("coding", "planner"), ("planning", "planner"),
                       ("tool", "planner"), ("red", "cyber"), ("soc", "cyber"),
                       ("purple", "cyber"), ("cyber", "cyber"), ("research", "deep")]:
        assert router.choose(task) == expected[role]


def test_workspace_access_and_traversal_controls_remain_enforced(tmp_path, monkeypatch):
    import tools.security
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "inside.txt").write_text("inside", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    monkeypatch.setattr(tools.security, "WORKSPACE_ROOT", root)
    manager = ToolManager()
    manager.discover()
    assert manager.execute("read_file", {"filename": "inside.txt"})["result"] == "inside"
    for target in ["../outside.txt", str(outside)]:
        result = manager.execute("read_file", {"filename": target})
        assert not result["success"]
        assert "outside Sentinel workspace" in result["error"]


def test_model_selected_tool_cannot_grant_itself_permission():
    from ai.dispatcher import Dispatcher

    class RestrictedTool(Tool):
        name = "restricted_test"
        description = "Records forbidden execution"
        category = "test"
        parameters = {}

        def execute(self):
            raise AssertionError("Restricted tool executed")

    manager = ToolManager()
    manager.registry.register(RestrictedTool())
    dispatcher = Dispatcher(Mock(), manager)
    result = dispatcher.dispatch("Execute it", {"type": "tool", "tool": "restricted_test", "parameters": {}})
    assert not result["success"]
    assert result["permission"] == "RESTRICTED"
    assert not ExecutionPolicy({PermissionClass.READ_ONLY}).allows(PermissionClass.STATE_CHANGE)
