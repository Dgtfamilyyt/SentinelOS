import json

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

            catalog.append(
                tool.info()
            )

        return json.dumps(
            catalog,
            indent=2
        )

    def _fast_path(self, prompt):

        """
        Fast deterministic path for extremely
        common built-in tool commands.

        This avoids calling an LLM just to interpret
        commands like 'list files'.
        """

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

            filename = (
                prompt.strip()[5:].strip()
            )

            return {
                "type": "tool",
                "task": "chat",
                "tool": "read_file",
                "parameters": {
                    "filename": filename
                },
            }

        if text.startswith(
            "create folder "
        ):

            folder = (
                prompt.strip()[14:].strip()
            )

            return {
                "type": "tool",
                "task": "chat",
                "tool": "create_folder",
                "parameters": {
                    "folder_name": folder
                },
            }

        return None

    def _fallback_task(self, prompt):

        """
        Lightweight fallback classification if
        the planner model returns invalid JSON.
        """

        text = prompt.lower()

        purple_words = [
            "purple team",
            "detection gap",
            "detect this attack",
            "attack detection",
        ]

        soc_words = [
            "soc",
            "blue team",
            "alert",
            "incident",
            "threat hunt",
            "ioc",
            "siem",
            "log analysis",
        ]

        red_words = [
            "red team",
            "pentest",
            "penetration test",
            "recon",
            "enumeration",
            "vulnerability",
            "exploit analysis",
        ]

        coding_words = [
            "python",
            "debug",
            "code",
            "programming",
            "function",
            "class",
            "traceback",
        ]

        if any(
            word in text
            for word in purple_words
        ):
            return "purple"

        if any(
            word in text
            for word in soc_words
        ):
            return "soc"

        if any(
            word in text
            for word in red_words
        ):
            return "red"

        if any(
            word in text
            for word in coding_words
        ):
            return "coding"

        return "chat"

    def _parse(self, raw, prompt):

        text = raw.strip()

        # Handle models that accidentally wrap
        # JSON inside Markdown fences.
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
                "task": (
                    self._fallback_task(prompt)
                ),
            }

        if not isinstance(plan, dict):

            return {
                "type": "chat",
                "task": (
                    self._fallback_task(prompt)
                ),
            }

        plan_type = plan.get(
            "type",
            "chat"
        )

        task = plan.get(
            "task",
            self._fallback_task(prompt)
        )

        if task not in self.VALID_TASKS:
            task = self._fallback_task(
                prompt
            )

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

            if not isinstance(
                parameters,
                dict
            ):
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

        fast = self._fast_path(prompt)

        if fast is not None:
            return fast

        planner_model = (
            self.router.choose(
                "planning"
            )
        )

        system_prompt = (
            PLANNER_PROMPT.format(
                tools=self._tool_catalog()
            )
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