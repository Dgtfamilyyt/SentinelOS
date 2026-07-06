from models.registry import ModelRegistry

registry = ModelRegistry()

print("Available Roles\n")

for role in registry.roles():

    model = registry.get(role)

    print(f"{role}")

    print(f"Model : {model['name']}")

    print(f"Role  : {model['role']}")

    print()