class IntentEngine:

    def classify(self, prompt: str):

        text = prompt.strip().lower()

        if "list files" in text:
            return {
                "type": "tool",
                "tool": "list_files",
                "parameters": {}
            }

        if "current directory" in text:
            return {
                "type": "tool",
                "tool": "current_directory",
                "parameters": {}
            }

        if text.startswith("read "):

            filename = (
                prompt.strip()[5:].strip()
            )

            return {
                "type": "tool",
                "tool": "read_file",
                "parameters": {
                    "filename": filename
                }
            }

        if text.startswith(
            "create folder "
        ):
            folder = (
                prompt.strip()[14:].strip()
            )

            return {
                "type": "tool",
                "tool": "create_folder",
                "parameters": {
                    "folder_name": folder
                }
            }

        return {
            "type": "chat",
            "task": "chat"
        }