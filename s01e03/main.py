import atexit
import os
import sys

from common import get_api_key

from s01e03.memory import InMemoryConversationMemory
from s01e03.brain import Brain
from s01e03.server import create_app

api_key = get_api_key()
openrouter_key = os.environ.get("OPENROUTER_API_KEY")
if not openrouter_key:
    print("OPENROUTER_API_KEY not set")
    sys.exit(1)

llm_model = os.environ.get("LLM_MODEL", "anthropic/claude-haiku-4.5")
llm_api_url = os.environ.get("LLM_API_URL", "https://openrouter.ai/api/v1/chat/completions")
use_mcp = os.environ.get("USE_MCP", "false").lower() == "true"

memory = InMemoryConversationMemory()

if use_mcp:
    from s01e03.mcp_packages_client import McpPackageService
    package_service = McpPackageService()
    package_service.connect()
    atexit.register(package_service.close)
    print("[Main] Using MCP package service")
else:
    from s01e03.packages import PackageService
    package_service = PackageService(api_key)
    print("[Main] Using direct API package service")

brain = Brain(openrouter_key, package_service, memory, model=llm_model, api_url=llm_api_url)
app = create_app(memory, brain)

atexit.register(memory.dump)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
