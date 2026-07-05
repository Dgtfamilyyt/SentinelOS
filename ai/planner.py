import json
from ollama import chat


class Planner:

    def __init__(self):
        self.model = "qwen3.6:latest"

    def plan(self, prompt: str):

        system_prompt = """
You are Sentinel's planning engine.

Your job is to decide whether the user needs a tool.

Available tools:

- list_files
- current_directory
- read_file
- create_folder

Return ONLY valid JSON.

Examples:

{
    "type":"tool",
    "tool":"list_files",
    "args":[]
}

or

{
    "type":"chat"
}
"""

        response = chat(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        try:
            return json.loads(response["message"]["content"])

        except Exception:

            return {
                "type": "chat"
            }