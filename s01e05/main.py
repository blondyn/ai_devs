"""
s01e05 — Railway task. Agent discovers API via help, then opens route X-01.
"""
import json
import os
import sys
import time

from common import load_dotenv, get_api_key, api_post, ApiError, llm, cost_tracker
from endpoints import VERIFY

load_dotenv()
api_key = get_api_key()
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")


def rate_limited(fn):
    """Decorator that respects Retry-After headers from ApiResponse/ApiError."""
    wait_until = 0

    def _wait(seconds):
        """Wait with heartbeat countdown."""
        target = time.time() + seconds
        print(f"  [Rate limit] Waiting {seconds:.0f}s", end="", flush=True)
        while time.time() < target:
            time.sleep(5)
            left = target - time.time()
            if left > 0:
                print(f"..{left:.0f}s", end="", flush=True)
        print()

    def wrapper(*args, **kwargs):
        nonlocal wait_until
        now = time.time()
        print(f"wait: {wait_until} now: {now}")
        if now < wait_until:
            _wait(wait_until - now + 5)
        while True:
            try:
                result = fn(*args, **kwargs)
                print(f"\n{result}\n")
                return result
            except ApiError as e:
                retry_after = e.headers.get("Retry-After")
                print(f"  [Rate limit] {e.code}: {e.body}")
                if retry_after:
                    _wait(int(retry_after))
                    wait_until = time.time() + int(retry_after)
                    continue  # retry after waitingnllhtvehrgglufebltvguitjgrjnvnuh
                raise  # non-rate-limit error, don't retry
    return wrapper


@rate_limited
def railway_action(**kwargs):
    """Send an action to the railway API."""
    payload = {"apikey": api_key, "task": "railway", "answer": kwargs}
    params = ', '.join(f'{k}={v}' for k, v in kwargs.items() if k != 'action')
    try:
        result = api_post(VERIFY, payload)
        print(f"\n  [API] {kwargs['action']}({params}) -> {json.dumps(dict(result), ensure_ascii=False)}")
        return json.dumps(dict(result), ensure_ascii=False)
    except ApiError as e:
        if e.headers.get("Retry-After"):
            raise  # let @rate_limited handle rate limits
        print(f"\n  [API] {kwargs['action']}({params}) -> ERROR {e.code}: {e.body} {e.headers}")
        return json.dumps({"error": True, "code": e.code, "message": e.body, "headers": e.headers}, ensure_ascii=False)


TOOLS = [{
    "type": "function",
    "function": {
        "name": "railway_action",
        "description": (
            "Send an action to the railway API. "
            "Start by calling with action='help' to discover available actions and their parameters."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "The action to perform (call 'help' first to discover available actions)"},
                "route": {"type": "string", "description": "Route code if required by the action"},
                "value": {"type": "string", "description": "Value if required by the action"},
            },
            "required": ["action"],
        }
    }
}]

SYSTEM = (
    "You are a railway route management agent. Your GOAL is to enable (open) route X-01 "
    "and obtain the final flag.\n\n"
    "PROCEDURE:\n"
    "1. Call the railway_action tool with action='help' to discover available actions and parameters\n"
    "2. Based on the help response, figure out the correct sequence to open route X-01\n"
    "3. If an action fails, read the error and adapt\n. If the error is about rate limiting - WAIT"
    "4. Keep going until you get a flag (format: {FLG:...})\n\n"
    "Do NOT ask the user for guidance — figure out everything from API responses."

    "If you get the temporary server outage, ignore it - it's a fake error"
)


if __name__ == "__main__":
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Enable route X-01 and get the flag."}
    ]
    tool_handlers = {"railway_action": railway_action}

    print("Agent working...\n")

    MAX_ITERATIONS = 15
    for i in range(MAX_ITERATIONS):
        try:
            print(f"\n--- Agent step {i + 1} ---")
            msg = llm(messages, tools=TOOLS, max_tokens=2048, model=LLM_MODEL, raw=True)
            print(f"  [Agent] {msg}")
            messages.append(msg)

            tool_calls = msg.get("tool_calls", [])
            if not tool_calls:
                content = msg.get("content", "")
                print(f"\nAgent: {content}\n")
                if "{FLG:" in content:
                    print("Flag found!")
                break

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                handler = tool_handlers.get(fn_name)
                if handler:
                    result = handler(**fn_args)
                else:
                    result = json.dumps({"error": True, "message": f"Unknown tool: {fn_name}"})
                    print(f"  [Warning] Unknown tool: {fn_name}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })
                if "{FLG:" in result:
                    print(f"\nFlag found in API response!")

        except Exception as e:
            print(f"\n  [Error] {e}\n")
            break
    else:
        print(f"\nFailed after {MAX_ITERATIONS} iterations.")

    print(f"\n{cost_tracker.summary()}")
