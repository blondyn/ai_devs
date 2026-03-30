import atexit
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import get_api_key

from memory import InMemoryConversationMemory
from packages import PackageService
from brain import Brain
from server import create_app

api_key = get_api_key()
openrouter_key = os.environ.get("OPENROUTER_API_KEY")
if not openrouter_key:
    print("OPENROUTER_API_KEY not set")
    sys.exit(1)

memory = InMemoryConversationMemory()
package_service = PackageService(api_key)
brain = Brain(openrouter_key, package_service, memory)
app = create_app(memory, brain)

atexit.register(memory.dump)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
