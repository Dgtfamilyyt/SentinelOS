from memory.persistent import PersistentMemory


class MemoryManager:

    def __init__(self):
        self.memory = PersistentMemory()

    def remember(self, key, value):
        self.memory.save(key, value)

    def recall(self, key, default=None):
        value = self.memory.load(key)

        if value is None:
            return default

        return value

    def forget(self, key):
        self.memory.delete(key)