import json
import os
import sys
import uuid
import urllib.request
from datetime import datetime

class ApiResponse(dict):
    """API response that behaves like a dict (body) but also exposes headers and status."""
    def __init__(self, body, headers, status):
        super().__init__(body)
        self.headers = headers
        self.status = status

def load_dotenv():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip()

load_dotenv()

BASE_URL = os.environ.get("API_BASE_URL", "https://hub.ag3nts.org")

def get_api_key():
    key = os.environ.get('AGENTS_KEY')
    if not key:
        print("AGENTS_KEY not set")
        sys.exit(1)
    return key

class ApiError(Exception):
    def __init__(self, code, body, headers=None):
        self.code = code
        self.body = body
        self.headers = dict(headers) if headers else {}
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
        raise ApiError(e.code, e.read().decode('utf-8'), e.headers)
    body = json.loads(resp.read().decode('utf-8'))
    headers = dict(resp.headers)
    return ApiResponse(body, headers, resp.status)

def _parse_json(content):
    import json
    return json.loads(content)


def _parse_csv(content):
    import csv
    import io
    return list(csv.DictReader(io.StringIO(content)))


def _parse_text(content):
    return content


# Built-in parsers for common formats
API_PARSERS = {
    "json": _parse_json,
    "csv": _parse_csv,
    "text": _parse_text,
}


def api_get(path, parser="json"):
    """Fetch data from API endpoint.

    Args:
        path: API endpoint path.
        parser: Either a string key from API_PARSERS ("json", "csv", "text"),
                or a callable that takes raw content and returns parsed data.

    Returns:
        Parsed response data.
    """
    with urllib.request.urlopen(f"{BASE_URL}{path}") as resp:
        content = resp.read().decode('utf-8')

    if callable(parser):
        return parser(content)

    parser_fn = API_PARSERS.get(parser)
    if not parser_fn:
        raise ValueError(f"Unknown parser: {parser}")
    return parser_fn(content)

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

def agent_loop(messages, tools, tool_handlers, max_iterations=10,
               model="google/gemini-2.0-flash-001", temperature=None, max_tokens=2048,
               on_tool_call=None):
    """Generic agent loop: LLM calls tools until it responds with text.

    Args:
        messages: Chat history (modified in place).
        tools: Tool definitions (OpenRouter function calling format).
        tool_handlers: Dict mapping tool name to callable.
        max_iterations: Max loop iterations before giving up.
        on_tool_call: Optional callback(name, args, result) for logging.

    Returns:
        (answer, messages) — answer is None if max iterations reached.
    """
    for i in range(max_iterations):
        msg = llm(messages, tools=tools, max_tokens=max_tokens,
                  temperature=temperature, model=model, raw=True)
        messages.append(msg)

        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            return msg.get("content", ""), messages

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"])
            handler = tool_handlers.get(fn_name)
            if handler:
                result = handler(**fn_args)
            else:
                result = f"Unknown tool: {fn_name}"
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)
            if on_tool_call:
                on_tool_call(fn_name, fn_args, result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

    return None, messages


def save_result(task_dir, data, prefix="result"):
    """Save data as JSON with timestamped filename in task_dir/results/."""
    output_dir = os.path.join(task_dir, "results")
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    filepath = os.path.join(output_dir, f"{prefix}_{ts}_{uid}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved to {filepath}")
    return filepath


def submit(api_key, task, answer):
    from endpoints import VERIFY
    result = api_post(VERIFY, {"apikey": api_key, "task": task, "answer": answer})
    print(f"Response: {json.dumps(result, indent=2)}")
    return result
