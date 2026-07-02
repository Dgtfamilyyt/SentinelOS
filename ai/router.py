from config.settings import GENERAL_MODEL, CODER_MODEL


class AIRouter:

    def get_model(self, prompt: str):

        prompt = prompt.lower()

        coding_keywords = [
            "code",
            "python",
            "java",
            "c++",
            "script",
            "bash",
            "powershell",
            "program",
            "function",
            "bug",
            "error"
        ]

        for keyword in coding_keywords:
            if keyword in prompt:
                return CODER_MODEL

        return GENERAL_MODEL