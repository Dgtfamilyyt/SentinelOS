from models.router import ModelRouter

router = ModelRouter()

print(router.choose("chat"))

print(router.choose("tool"))

print(router.choose("cyber"))

print(router.choose("research"))