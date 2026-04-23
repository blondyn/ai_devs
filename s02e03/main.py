import json
import logging

import tiktoken
from common import api_get, interactive_agent_loop, get_api_key, submit
from endpoints import DATA_FAILURE

logger = logging.getLogger(__name__)

API_KEY = get_api_key()

SYSTEM_PROMPT = """You are a helpful assistant with access to tools. \
You can chain multiple tools together to complete tasks. \
For example, you can filter logs first, then count tokens on the result. \
Always use the output of one tool as input to the next when the user asks for a multi-step operation."""


def count_tokens(text, model="gpt-4o"):
    """Count tokens in text using tiktoken."""
    enc = tiktoken.encoding_for_model(model)
    count = len(enc.encode(text))
    return json.dumps({"token_count": count, "model": model, "text_length": len(text)})

def get_failure_log():
    """Get the failure log data."""
    return api_get(DATA_FAILURE.format(api_key=API_KEY), "text")

def filter_logs(levels):
    """Return log lines matching the specified levels."""
    logs = api_get(DATA_FAILURE.format(api_key=API_KEY), "text")
    filtered = [line for line in logs.splitlines() if any(f"[{l}]" in line for l in levels)]
    return "\n".join(filtered)


def slice_logs(start=0, count=10):
    """Return a subset of log lines. Use negative start for lines from the end."""
    logs = api_get(DATA_FAILURE.format(api_key=API_KEY), "text")
    lines = logs.splitlines()
    if start < 0:
        sliced = lines[start:][:count]
    else:
        sliced = lines[start:start + count]
    return json.dumps({"total_lines": len(lines), "returned": len(sliced), "start": start, "lines": "\n".join(sliced)})


def submit_answer(logs):
    """Submit the answer for the failure task."""
    from common import ApiError
    try:
        result = submit(api_key=API_KEY, task="failure", answer={"logs": logs})
        return json.dumps({"status": "ok", "code": result.status, "response": result.body})
    except ApiError as e:
        return json.dumps({"status": "error", "code": e.code, "response": e.body, "submitted": logs[:200]})


def get_log_levels():
    """Analyze failure logs and return available log levels."""
    import re
    logs = api_get(DATA_FAILURE.format(api_key=API_KEY), "text")
    levels = sorted(set(re.findall(r'\[(\w+)\]', logs)))
    return json.dumps({"levels": levels, "count": {l: logs.count(f"[{l}]") for l in levels}})


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "count_tokens",
            "description": "Count the number of tokens in a given text using tiktoken. Useful for estimating API costs or checking context window limits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to count tokens for"},
                    "model": {"type": "string", "description": "Model to use for tokenization (default: gpt-4o)", "default": "gpt-4o"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_failure_log",
            "description": "Get the logs for all levels of the logs (e.g. ERROR, WARNING, INFO).",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_log_levels",
            "description": "Analyze failure logs and return available log levels with their counts.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_logs",
            "description": "Return log lines matching the specified log levels (e.g. ['ERROR', 'WARN']).",
            "parameters": {
                "type": "object",
                "properties": {
                    "levels": {"type": "array", "items": {"type": "string"}, "description": "Log levels to filter by"},
                },
                "required": ["levels"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "slice_logs",
            "description": "Return a subset of log lines. Use start=0 for first lines, start=-10 for last 10 lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "integer", "description": "Starting line index. Negative values count from the end (e.g. -10 for last 10 lines).", "default": 0},
                    "count": {"type": "integer", "description": "Number of lines to return.", "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": "Submit the answer for the failure task. Pass the log content as a string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "logs": {"type": "string", "description": "The log content to submit as the answer"},
                },
                "required": ["logs"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "count_tokens": count_tokens,
    "get_failure_log": get_failure_log,
    "get_log_levels": get_log_levels,
    "filter_logs": filter_logs,
    "slice_logs": slice_logs,
    "submit_answer": submit_answer,
}



GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def on_tool_call(name, args, result):
    logger.info(f"{YELLOW}Tool: {name}({json.dumps(args)}) -> {result}{RESET}")


def chat():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input(f"\n{GREEN}You: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            break

        messages.append({"role": "user", "content": user_input})

        answer, messages = interactive_agent_loop(
            messages,
            tools=TOOLS or None,
            tool_handlers=TOOL_HANDLERS,
            on_tool_call=on_tool_call,
        )

        if answer:
            print(f"\n{CYAN}Assistant:{RESET} {answer}")
        else:
            print("\n[No response - max iterations reached]")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    chat()
