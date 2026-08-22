class Dispatcher:

    def __init__(
        self,
        ai_engine,
        tool_manager
    ):
        self.ai = ai_engine
        self.tools = tool_manager

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