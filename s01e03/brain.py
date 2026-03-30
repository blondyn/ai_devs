import json
import urllib.request
from packages import PackageService
from memory import ConversationMemory

SYSTEM_PROMPT = """You are a helpful assistant that can check and redirect packages.

You have access to tools for managing packages:
- check_package: Check the status of a package by its ID
- redirect_package: Redirect a package to a new destination (requires package ID, destination code, and security code)

Be concise and helpful. When a user asks about a package, use the appropriate tool."""

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "check_package",
            "description": "Check the status of a package by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_id": {"type": "string", "description": "Package ID, e.g. PKG12345678"},
                },
                "required": ["package_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "redirect_package",
            "description": "Redirect a package to a new destination.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_id": {"type": "string", "description": "Package ID"},
                    "destination": {"type": "string", "description": "Destination code, e.g. PWR3847PL"},
                    "code": {"type": "string", "description": "Security code"},
                },
                "required": ["package_id", "destination", "code"],
            },
        },
    },
]


class Brain:
    def __init__(self, openrouter_key: str, package_service: PackageService, memory: ConversationMemory,
                 model: str = "google/gemini-2.0-flash-001"):
        self._openrouter_key = openrouter_key
        self._package_service = package_service
        self._memory = memory
        self._model = model
        self._tools_map = {
            "check_package": lambda package_id: self._package_service.check(package_id),
            "redirect_package": lambda package_id, destination, code: self._package_service.redirect(package_id, destination, code),
        }

    def _call_openrouter(self, messages: list[dict]) -> dict:
        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "tools": TOOLS_SCHEMA,
            "max_tokens": 4096,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._openrouter_key}",
            },
        )
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read().decode("utf-8"))

    def think(self, session_id: str, user_msg: str) -> str:
        history = self._memory.get(session_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for entry in history:
            messages.append({"role": entry["role"], "content": entry["msg"]})

        messages.append({"role": "user", "content": user_msg})

        max_iterations = 5
        for _ in range(max_iterations):
            result = self._call_openrouter(messages)
            message = result["choices"][0]["message"]
            messages.append(message)

            tool_calls = message.get("tool_calls", [])
            if not tool_calls:
                return message.get("content", "")

            for tc in tool_calls:
                func_name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"]) if tc["function"].get("arguments") else {}
                print(f"  [Brain] Calling {func_name}({args})")

                func = self._tools_map.get(func_name)
                if func:
                    try:
                        tool_result = func(**args)
                    except Exception as e:
                        tool_result = {"error": str(e)}
                else:
                    tool_result = {"error": f"Unknown tool: {func_name}"}

                print(f"  [Brain] Result: {json.dumps(tool_result, ensure_ascii=False)[:200]}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })

        return "I wasn't able to complete the request in time."
