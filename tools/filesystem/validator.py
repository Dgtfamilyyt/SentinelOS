class ToolValidator:

    REQUIRED_FIELDS = [
        "name",
        "description",
        "category",
        "parameters",
    ]

    def validate(self, tool):

        errors = []

        for field in self.REQUIRED_FIELDS:

            value = getattr(tool, field, None)

            if value is None:
                errors.append(f"Missing field: {field}")

            elif value == "":
                errors.append(f"Empty field: {field}")

        if not callable(getattr(tool, "execute", None)):
            errors.append("Missing execute() method")

        return errors