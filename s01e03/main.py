import atexit
from memory import InMemoryConversationMemory
from server import create_app

memory = InMemoryConversationMemory()
app = create_app(memory)

atexit.register(memory.dump)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
