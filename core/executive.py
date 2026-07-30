class ExecutiveBrain:

    def __init__(self):
        pass

    def decide(self, prompt):

        return {
            "intent": "chat",
            "use_tools": False,
            "use_memory": True,
            "save_memory": False,
            "model": "general"
        }