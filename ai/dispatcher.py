class Dispatcher:

    def __init__(
        self,
        ai_engine,
        tool_manager
    ):
        self.ai = ai_engine
        self.tools = tool_manager

    async def dispatch_stream(self, prompt, plan, **context):
        from contextlib import aclosing

        if plan.get("type") == "tool":
            yield {"type": "status", "stage": "tool"}
            result = self.tools.execute(plan.get("tool"), plan.get("parameters", {}))
            yield {"type": "tool_result", "result": result}
            return
        if plan.get("type") != "chat":
            raise ValueError("Unknown plan type")
        async with aclosing(self.ai.ask_stream(prompt, task=plan.get("task", "chat"), **context)) as events:
            async for event in events:
                yield event

    def dispatch(
        self,
        prompt,
        plan
    ):

        plan_type = plan.get(
            "type"
        )

        task = plan.get(
            "task",
            "chat"
        )

        if plan_type == "tool":

            tool_name = plan.get(
                "tool"
            )

            parameters = plan.get(
                "parameters",
                {}
            )

            return self.tools.execute(
                tool_name,
                parameters
            )

        if plan_type == "chat":

            return self.ai.ask(
                prompt,
                task=task
            )

        return {
            "success": False,
            "error": (
                f"Unknown plan type: "
                f"{plan_type}"
            ),
        }
