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

    def validate_parameters(self, tool, parameters):

        errors = []

        if parameters is None:
            parameters = {}

        required = tool.parameters

        if isinstance(required, dict):
            required_names = required.keys()

        elif isinstance(required, list):
            required_names = required

        else:
            return ["Invalid parameters definition"]

        for name in required_names:

            if name not in parameters:
                errors.append(
                    f"Missing required parameter: {name}"
                )

        return errors