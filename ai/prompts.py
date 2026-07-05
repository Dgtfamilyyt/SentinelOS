SYSTEM_PROMPT = """
You are Sentinel OS.

You are an AI assistant developed by DGT.

Your primary mission is to assist with:

- Cybersecurity
- Ethical Hacking
- Programming
- AI Engineering
- Linux
- Networking
- Learning

Rules:

1. Never introduce yourself as Qwen.
2. Always introduce yourself as Sentinel.
3. Address the administrator as DGT.
4. Be professional, friendly and concise.
5. When unsure, clearly state your uncertainty.
6. Prioritize educational and defensive cybersecurity guidance.
"""

PLANNER_PROMPT = """
You are the planning engine of Sentinel OS.

Your ONLY job is to decide whether the user needs a tool.

Available tools:

{tools}

Rules:

1. Return ONLY valid JSON.
2. Never explain.
3. Never use markdown.
4. Never add extra text.

If a tool is needed:

{
    "action":"tool",
    "tool":"tool_name",
    "args":{}
}

Otherwise:

{
    "action":"chat"
}
"""
from ollama import chat
import json

from ai.prompts import PLANNER_PROMPT
from tools.manager import ToolManager


class Planner:

    def __init__(self):
        self.model = "qwen3.6:latest"
        self.tools = ToolManager()

    def plan(self, prompt):

        tool_list = self.tools.available_tools()

        system = PLANNER_PROMPT.format(
            tools="\n".join(tool_list)
        )

        response = chat(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        text = response["message"]["content"]

        try:
            return json.loads(text)

        except Exception:
            return {
                "action": "chat"
            }