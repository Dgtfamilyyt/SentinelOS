from memory.persistent import PersistentMemory

memory = PersistentMemory()

memory.save("admin", "DGT")

print(memory.load("admin"))