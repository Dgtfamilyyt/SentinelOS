class Dispatcher:

    def __init__(self, ai_engine, tool_manager):
        self.ai = ai_engine
        self.tools = tool_manager

    def dispatch(self, prompt, intent):
        intent_type = intent.get("type")

        if intent_type == "tool":
            tool_name = intent.get("tool")
            parameters = intent.get("parameters", {})

            return self.tools.execute(
                tool_name,
                parameters
            )

        if intent_type == "chat":
            task = intent.get("task", "chat")

            return self.ai.ask(
                prompt,
                task=task
            )

        return {
            "success": False,
            "error": f"Unknown intent type: {intent_type}"
        }
