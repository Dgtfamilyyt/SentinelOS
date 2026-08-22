class ToolValidator:

    REQUIRED_FIELDS = [
        "name",
        "description",
        "category",
        "parameters",
    ]

    TYPE_MAP = {
        "string": str,
        "integer": int,
        "float": float,
        "boolean": bool,
        "list": list,
        "dict": dict,
    }

    def validate(self, tool):
        errors = []

        for field in self.REQUIRED_FIELDS:
            value = getattr(tool, field, None)

            if value is None:
                errors.append(
                    f"Missing field: {field}"
                )

            elif field != "parameters" and value == "":
                errors.append(
                    f"Empty field: {field}"
                )

        if not isinstance(tool.parameters, dict):
            errors.append(
                "parameters must be a dictionary"
            )

            return errors

        for name, spec in tool.parameters.items():

            if not isinstance(spec, dict):
                errors.append(
                    f"Parameter '{name}' must use "
                    f"the standard schema"
                )
                continue

            param_type = spec.get("type")

            if param_type not in self.TYPE_MAP:
                errors.append(
                    f"Invalid type for parameter "
                    f"'{name}': {param_type}"
                )

        if not callable(
            getattr(tool, "execute", None)
        ):
            errors.append(
                "Missing execute() method"
            )

        return errors

    def prepare_parameters(
        self,
        tool,
        parameters=None
    ):
        if parameters is None:
            parameters = {}

        if not isinstance(parameters, dict):
            return {}, [
                "Tool parameters must be a dictionary"
            ]

        errors = []
        prepared = {}

        definitions = tool.parameters

        # Reject unexpected arguments
        for name in parameters:

            if name not in definitions:
                errors.append(
                    f"Unknown parameter: {name}"
                )

        for name, spec in definitions.items():

            required = spec.get(
                "required",
                False
            )

            if name in parameters:
                value = parameters[name]

            elif "default" in spec:
                value = spec["default"]

            elif required:
                errors.append(
                    f"Missing required parameter: {name}"
                )
                continue

            else:
                continue

            expected_name = spec.get("type")
            expected_type = self.TYPE_MAP.get(
                expected_name
            )

            if (
                expected_type is not None
                and not isinstance(
                    value,
                    expected_type
                )
            ):
                errors.append(
                    f"Parameter '{name}' must be "
                    f"{expected_name}"
                )
                continue

            prepared[name] = value

        return prepared, errors

    def validate_parameters(
        self,
        tool,
        parameters
    ):
        _, errors = self.prepare_parameters(
            tool,
            parameters
        )

        return errors