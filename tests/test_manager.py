from memory.manager import MemoryManager

memory = MemoryManager()

memory.remember("favorite_language", "Python")

print(memory.recall("favorite_language"))

memory.forget("favorite_language")

print(memory.recall("favorite_language", "Unknown"))