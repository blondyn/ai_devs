import atexit
import os
import sys

from common import get_api_key

from s01e03.memory import InMemoryConversationMemory
from s01e03.packages import PackageService
from s01e03.brain import Brain
from s01e03.server import create_app

api_key = get_api_key()
openrouter_key = os.environ.get("OPENROUTER_API_KEY")
server_port = os.environ.get("PORT")
if not openrouter_key:
    print("OPENROUTER_API_KEY not set")
    sys.exit(1)

memory = InMemoryConversationMemory()
package_service = PackageService(api_key)
brain = Brain(openrouter_key, package_service, memory)
app = create_app(memory, brain)

atexit.register(memory.dump)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
