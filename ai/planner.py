import json
import re
from contextlib import aclosing

from ai.client import AIClient
from ai.prompts import PLANNER_PROMPT
from models.router import ModelRouter


class Planner:

    VALID_TASKS = {
        "chat",
        "coding",
        "red",
        "soc",
        "blue",
        "purple",
        "cyber",
    }

    def __init__(self, tool_manager):
        self.tools = tool_manager
        self.client = AIClient()
        self.router = ModelRouter()

    def _tool_catalog(self):

        catalog = []

        for tool in self.tools.all():
            catalog.append(tool.info())

        return json.dumps(
            catalog,
            indent=2
        )

    def _fast_path(self, prompt):

        text = prompt.strip().lower()

        if text in {
            "list files",
            "show files",
            "show workspace files",
        }:
            return {
                "type": "tool",
                "task": "chat",
                "tool": "list_files",
                "parameters": {},
            }

        if text in {
            "current directory",
            "current workspace",
            "show current directory",
        }:
            return {
                "type": "tool",
                "task": "chat",
                "tool": "current_directory",
                "parameters": {},
            }

        if text.startswith("read "):

            filename = prompt.strip()[5:].strip()

            return {
                "type": "tool",
                "task": "chat",
                "tool": "read_file",
                "parameters": {
                    "filename": filename
                },
            }

        if text.startswith("create folder "):

            folder = prompt.strip()[14:].strip()

            return {
                "type": "tool",
                "task": "chat",
                "tool": "create_folder",
                "parameters": {
                    "folder_name": folder
                },
            }

        return None

    def _strong_task_hint(self, prompt):

        text = prompt.lower()

        # Purple FIRST because purple-team requests
        # often contain both red and SOC terminology.
        purple_signals = [
            "purple team",
            "purple-team",
            "detection gap",
            "detection coverage",
            "attack detection",
            "detect this attack",
            "telemetry should detect",
            "attack vs detection",
            "red-team technique with telemetry",
        ]

        red_signals = [
            "authorized penetration test",
            "penetration test",
            "pentest",
            "red team",
            "red-team",
            "reconnaissance",
            "recon result",
            "enumeration",
            "exploit research",
            "attack surface",
            "exposed services",
            "vulnerability assessment",
        ]

        soc_signals = [
            "soc",
            "blue team",
            "blue-team",
            "siem",
            "alert triage",
            "incident response",
            "threat hunt",
            "threat hunting",
            "ioc",
            "log analysis",
            "authentication logs",
            "security alert",
        ]

        coding_signals = [
            "traceback",
            "debug this code",
            "python code",
            "programming",
            "software bug",
            "fix this code",
        ]

        if any(
            signal in text
            for signal in purple_signals
        ):
            return "purple"

        if any(
            signal in text
            for signal in red_signals
        ):
            return "red"

        if any(
            signal in text
            for signal in soc_signals
        ):
            return "soc"

        if any(
            signal in text
            for signal in coding_signals
        ):
            return "coding"

        return None

    def _fallback_task(self, prompt):

        strong_hint = self._strong_task_hint(prompt)

        if strong_hint is not None:
            return strong_hint

        return "chat"

    def _parse(self, raw, prompt):

        text = raw.strip()

        # Remove accidental markdown fences.
        if text.startswith("```"):

            lines = text.splitlines()

            if lines:
                lines = lines[1:]

            if (
                lines
                and lines[-1].strip() == "```"
            ):
                lines = lines[:-1]

            text = "\n".join(lines).strip()

        try:
            plan = json.loads(text)

        except json.JSONDecodeError:
            return {
                "type": "chat",
                "task": self._fallback_task(prompt),
            }

        if not isinstance(plan, dict):
            return {
                "type": "chat",
                "task": self._fallback_task(prompt),
            }

        plan_type = plan.get(
            "type",
            "chat"
        )

        task = plan.get(
            "task",
            self._fallback_task(prompt)
        )

        # Strong deterministic signals override
        # incorrect LLM classification.
        strong_hint = self._strong_task_hint(prompt)

        if strong_hint is not None:
            task = strong_hint

        if task not in self.VALID_TASKS:
            task = self._fallback_task(prompt)

        if plan_type == "tool":

            tool_name = plan.get("tool")

            if tool_name not in self.tools.names():
                return {
                    "type": "chat",
                    "task": task,
                }

            parameters = plan.get(
                "parameters",
                {}
            )

            if not isinstance(parameters, dict):
                parameters = {}

            return {
                "type": "tool",
                "task": task,
                "tool": tool_name,
                "parameters": parameters,
            }

        return {
            "type": "chat",
            "task": task,
        }

    def plan(self, prompt):

        fast = self.quick_plan(prompt)

        if fast is not None:
            return fast

        planner_model = self.router.choose(
            "planning"
        )

        system_prompt = PLANNER_PROMPT.format(
            tools=self._tool_catalog()
        )

        raw = self.client.generate(
            model=planner_model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )

        return self._parse(
            raw,
            prompt
        )

    def quick_plan(self, prompt):
        fast = self._fast_path(prompt)
        if fast is not None:
            return fast
        action = re.search(r"\b(open|read|list|show|create|make|mkdir|display|find)\b", prompt, re.I)
        resource = re.search(r"\b(file|files|folder|folders|directory|directories|workspace)\b|\.[a-z0-9]{1,8}\b", prompt, re.I)
        if action and resource:
            return None
        return {"type": "chat", "task": self._fallback_task(prompt)}

    async def plan_stream(self, prompt, runtime, model=None):
        from ai.streaming import stream_model

        yield {"type": "status", "stage": "routing"}
        plan = self.quick_plan(prompt)
        if plan is None:
            raw = ""
            messages = [{"role": "system", "content": PLANNER_PROMPT.format(tools=self._tool_catalog())},
                        {"role": "user", "content": prompt}]
            async with aclosing(stream_model(runtime, model or self.router.choose("planning"), messages, planning=True)) as events:
                async for event in events:
                    if event["type"] == "delta":
                        raw += event["text"]
                    else:
                        yield event
            plan = self._parse(raw, prompt)
        yield {"type": "plan", "plan": plan}
