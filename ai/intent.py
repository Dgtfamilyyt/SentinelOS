class IntentEngine:

    def classify(self, prompt: str):

        text = prompt.lower()

        if "list files" in text:
            return {
                "type": "tool",
                "tool": "list_files",
                "args": []
            }

        if "current directory" in text:
            return {
                "type": "tool",
                "tool": "current_directory",
                "args": []
            }

        if text.startswith("read "):

            filename = prompt[5:]

            return {
                "type": "tool",
                "tool": "read_file",
                "args": [filename]
            }

        if text.startswith("create folder "):

            folder = prompt[14:]

            return {
                "type": "tool",
                "tool": "create_folder",
                "args": [folder]
            }

        return {
            "type": "chat"
        }