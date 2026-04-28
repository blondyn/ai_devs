import json
import logging

import tiktoken
from common import api_get, interactive_agent_loop, get_api_key, submit, pause_spinner, resume_spinner
from endpoints import DATA_FAILURE

logger = logging.getLogger(__name__)

API_KEY = get_api_key()

SYSTEM_PROMPT = """You are a failure-log analysis assistant. You have access to tools for fetching, filtering, and submitting logs.

Rules for every response:
1. NEVER paste raw log lines into your reply. Instead summarise what the tool returned: state how many lines matched, what log levels were present, and one or two representative patterns you noticed.
2. After reporting facts, interpret what they mean — e.g. "3 consecutive CRITICAL errors from the database module suggest connection pool exhaustion."
3. Always end with a concrete next step: a specific tool call you recommend next, or a hypothesis to test.
4. Keep replies concise — a few sentences of summary, one sentence of interpretation, one sentence of suggestion.

Submission rule: submit_answer must receive newline-separated log lines. Each line must preserve the original format: timestamp and log level (e.g. "[2026-04-27 06:04] [CRIT] ..."). The message part of each line may be condensed or rewritten to save tokens, but the timestamp and level prefix must remain intact.
"""


def count_tokens(text, model="gpt-4o"):
    """Count tokens in text using tiktoken."""
    enc = tiktoken.encoding_for_model(model)
    count = len(enc.encode(text))
    return json.dumps({"token_count": count, "model": model, "text_length": len(text)})

_log_lines = None

def _fetch_log_lines() -> list[str]:
    global _log_lines
    if _log_lines is None:
        _log_lines = api_get(DATA_FAILURE.format(api_key=API_KEY), "text").splitlines()
    return _log_lines

def get_failure_log():
    """Return total line count of the failure log."""
    return json.dumps({"total_lines": len(_fetch_log_lines())})

def filter_logs(levels):
    """Return log lines matching the specified levels (filtered locally)."""
    matched = [l for l in _fetch_log_lines() if any(f"[{lvl}]" in l for lvl in levels)]
    return json.dumps({"matched_lines": len(matched), "levels": levels, "lines": "\n".join(matched)})

def search_logs(query):
    """Return log lines containing the query string (case-insensitive)."""
    q = query.lower()
    matched = [l for l in _fetch_log_lines() if q in l.lower()]
    return json.dumps({"matched_lines": len(matched), "query": query, "lines": "\n".join(matched)})


_cache = []

def insert_cache(content):
    """Append a processed insight string to the in-memory cache."""
    _cache.append(content)
    return json.dumps({"status": "ok", "entries": len(_cache)})

def clear_cache():
    """Clear all entries from the in-memory cache."""
    _cache.clear()
    return json.dumps({"status": "ok", "entries": 0})

def read_cache():
    """Return all cache entries joined as a single string."""
    return "\n".join(_cache) if _cache else ""



def submit_answer(logs):
    """Submit the answer for the failure task."""
    global _submission_done
    import os
    from datetime import datetime
    from common import ApiError

    submissions_dir = os.path.join(os.path.dirname(__file__), "submissions")
    os.makedirs(submissions_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        result = submit(api_key=API_KEY, task="failure", answer={"logs": logs})
        outcome = {"status": "ok", "code": result.status, "response": result.body}
    except ApiError as e:
        outcome = {"status": "error", "code": e.code, "response": e.body, "submitted": logs[:200]}        


    record = {"request": {"task": "failure", "answer": {"logs": logs}}, "response": outcome}
    path = os.path.join(submissions_dir, f"{timestamp}.json")
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    logger.info(f"Submission saved to {path}")

    return json.dumps(outcome)


def get_log_levels():
    """Analyze failure logs and return available log levels."""
    import re
    lines = _fetch_log_lines()
    text = "\n".join(lines)
    levels = sorted(set(re.findall(r'\[(\w+)\]', text)))
    return json.dumps({"levels": levels, "count": {l: text.count(f"[{l}]") for l in levels}})


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
            "description": "Return the total line count of the failure log. Use this to learn how many lines exist before slicing.",
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
            "description": "Return log lines matching the specified log levels. Filtering runs locally — only relevant lines are returned, not the full log.",
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
            "name": "search_logs",
            "description": "Return log lines containing the given query string (case-insensitive substring match). Runs locally on the fetched log — the full log is never sent to you.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Substring to search for in log lines"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_cache",
            "description": "Append a log entry or insight to the in-memory cache. Use this to accumulate the lines you intend to submit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The log line or summary to store"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_cache",
            "description": "Return all cached entries as a single string. Pass this to count_tokens or submit_answer.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_cache",
            "description": "Clear all entries from the cache.",
            "parameters": {"type": "object", "properties": {}},
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
    "search_logs": search_logs,
    "insert_cache": insert_cache,
    "read_cache": read_cache,
    "clear_cache": clear_cache,
    "submit_answer": submit_answer,
}



GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def on_iteration(i, max_iterations):
    logger.info(f"{CYAN}[iteration {i + 1}/{max_iterations}] calling LLM...{RESET}")

def on_tool_start(name, args):
    logger.info(f"{YELLOW}→ {name}({json.dumps(args)}){RESET}")

def on_tool_call(name, args, result):
    lines = result.splitlines()
    preview = "\n    ".join(lines[:5])
    suffix = f"\n    ... ({len(lines)} lines total)" if len(lines) > 5 else ""
    logger.info(f"{YELLOW}← {name}:\n    {preview}{suffix}{RESET}")


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
        if user_input.lower() == "preview":
            import os
            content = "\n".join(_cache) if _cache else ""
            if not content:
                print(f"{YELLOW}Cache is empty — nothing to preview.{RESET}")
            else:
                path = os.path.join(os.path.dirname(__file__), "preview.log")
                with open(path, "w") as f:
                    f.write(content)
                print(f"{CYAN}Saved {len(_cache)} entries to {path}{RESET}")
            continue

        messages.append({"role": "user", "content": user_input})
        pre_run_len = len(messages)

        def make_handler(name, fn):
            def wrapped(**kwargs):
                on_tool_start(name, kwargs)
                if name == "submit_answer":
                    pause_spinner()
                    try:
                        confirm = input(f"\n{YELLOW}Submit? [y/N]: {RESET}").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        confirm = "n"
                    finally:
                        resume_spinner()
                    if confirm != "y":
                        return json.dumps({"status": "cancelled", "message": "User declined submission."})
                return fn(**kwargs)
            return wrapped

        instrumented = {name: make_handler(name, fn) for name, fn in TOOL_HANDLERS.items()}

        try:
            answer, messages = interactive_agent_loop(
                messages,
                tools=TOOLS or None,
                tool_handlers=instrumented,
                on_tool_call=on_tool_call,
                on_iteration=on_iteration,
            )
        except KeyboardInterrupt:
            messages = messages[:pre_run_len - 1]
            print(f"\n{YELLOW}[Interrupted — back to prompt]{RESET}")
            continue

        if answer:
            print(f"\n{CYAN}Assistant:{RESET} {answer}")
        else:
            print("\n[No response - max iterations reached]")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    chat()
