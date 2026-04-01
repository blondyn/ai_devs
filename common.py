import json
import os
import sys
import urllib.request

BASE_URL = os.environ.get("API_BASE_URL", "https://hub.ag3nts.org")

def load_dotenv():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip()

def get_api_key():
    load_dotenv()
    key = os.environ.get('AGENTS_KEY')
    if not key:
        print("AGENTS_KEY not set")
        sys.exit(1)
    return key

class ApiError(Exception):
    def __init__(self, code, body):
        self.code = code
        self.body = body
        super().__init__(f"HTTP {code}: {body}")


class CostTracker:
    """Tracks cumulative LLM usage and cost across calls."""
    def __init__(self):
        self.total_cost = 0.0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.calls = 0

    def add(self, usage):
        self.calls += 1
        self.total_cost += usage.get("cost", 0) or 0
        self.total_prompt_tokens += usage.get("prompt_tokens", 0)
        self.total_completion_tokens += usage.get("completion_tokens", 0)

    def summary(self):
        return (
            f"LLM calls: {self.calls} | "
            f"Tokens: {self.total_prompt_tokens} in / {self.total_completion_tokens} out | "
            f"Cost: ${self.total_cost:.6f}"
        )

cost_tracker = CostTracker()

def api_post(endpoint, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}{endpoint}", data=data,
                                headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode('utf-8'))
    return json.loads(resp.read().decode('utf-8'))

def api_get(path):
    with urllib.request.urlopen(f"{BASE_URL}{path}") as resp:
        return json.loads(resp.read().decode('utf-8'))

def llm(messages, schema=None, tools=None, max_tokens=1024, temperature=None,
        model="google/gemini-2.0-flash-001", raw=False):
    """Unified LLM call via OpenRouter. Supports structured output, tool use, and vision.

    Args:
        messages: Chat messages (can include multimodal content).
        schema: JSON schema for structured output (response_format).
        tools: Tool definitions for function calling.
        max_tokens: Max response tokens.
        temperature: Sampling temperature.
        model: OpenRouter model ID.
        raw: If True, return the full message object (useful for tool_calls).

    Returns:
        - If raw: full message dict from the API.
        - If schema: parsed JSON object.
        - Otherwise: content string.
    """
    openrouter_key = os.environ.get('OPENROUTER_API_KEY')
    if not openrouter_key:
        print("OPENROUTER_API_KEY not set")
        sys.exit(1)
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if schema:
        body["response_format"] = schema
    if tools:
        body["tools"] = tools
    if temperature is not None:
        body["temperature"] = temperature
    payload = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {openrouter_key}"}
    )
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
        sys.exit(1)
    result = json.loads(resp.read().decode('utf-8'))
    if "usage" in result:
        cost_tracker.add(result["usage"])
    msg = result['choices'][0]['message']
    if raw:
        return msg
    content = msg.get('content', '')
    if schema and content:
        return json.loads(content)
    return content


def llm_call(messages, schema, max_tokens=1024, model="google/gemini-2.0-flash-001"):
    """Structured output LLM call. Returns parsed JSON."""
    return llm(messages, schema=schema, max_tokens=max_tokens, model=model)


def llm_vision_call(messages, schema=None, max_tokens=1024, model="google/gemini-2.0-flash-001"):
    """LLM call with vision support. Returns parsed JSON if schema given, else string."""
    return llm(messages, schema=schema, max_tokens=max_tokens, model=model)

def submit(api_key, task, answer):
    from endpoints import VERIFY
    result = api_post(VERIFY, {"apikey": api_key, "task": task, "answer": answer})
    print(f"Response: {json.dumps(result, indent=2)}")
    return result
