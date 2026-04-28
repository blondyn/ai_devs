import json
import logging
import re

import tiktoken
from common import (
    api_get, interactive_agent_loop, get_api_key, submit, llm,
    pause_spinner, resume_spinner, cost_tracker,
)
from endpoints import DATA_FAILURE

logger = logging.getLogger(__name__)
API_KEY = get_api_key()

SYSTEM_PROMPT = """You are a failure-log analysis assistant.

Rules:
1. Never paste raw log lines. Summarise counts and patterns.
2. Interpret what the data means.
3. Suggest next steps. Wait for permission before acting.

Workflow:
- Use get_log_levels or filter_logs to explore the data.
- Call prepare_submission with the desired levels. Pass deduplicate=true to reduce
  repeated messages before compression (recommended). Python chunks the lines and
  compresses message text via a separate LLM call — you never see raw content.
- prepare_submission reports exact token count. Target is under 1500 tokens.
- Call submit_answer with no arguments once ready.
"""

COMPRESSION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "compressed_chunk",
        "schema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {"type": "string"},
                }
            },
            "required": ["messages"],
            "additionalProperties": False,
        },
    },
}

CHUNK_SIZE = 50

_log_lines = None
_prepared = None


def _fetch_log_lines():
    global _log_lines
    if _log_lines is None:
        _log_lines = api_get(DATA_FAILURE.format(api_key=API_KEY), "text").splitlines()
    return _log_lines


def _compact_timestamp(line):
    return re.sub(r'\[(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):\d{2}\]', r'[\1 \2:\3]', line)


def _dedup_by_message(lines):
    seen, out = set(), []
    for l in lines:
        msg = l.split('] ', 2)[-1]
        if msg not in seen:
            out.append(l)
            seen.add(msg)
    return out


def _compress_chunk(lines):
    """Return compressed message strings for each line via structured LLM call."""
    messages = [
        {
            "role": "system",
            "content": (
                f"Shorten each log message to 3-5 words. "
                f"Return exactly {len(lines)} strings in the same order as input. "
                "Rules: always keep uppercase identifiers (component names like ECCS8, WTRPMP, STMTURB12, WTANK07, FIRMWARE, PWR01). "
                "Drop the log level word if it appears in the message text. "
                "Keep the failure mode or action. "
                "Drop boilerplate endings like 'is required', 'are required', 'is terminated'."
            ),
        },
        {"role": "user", "content": "\n".join(lines)},
    ]
    result = llm(messages, schema=COMPRESSION_SCHEMA, max_tokens=1024)
    compressed = result.get("messages", [])
    if len(compressed) != len(lines):
        logger.warning(f"Chunk mismatch: expected {len(lines)}, got {len(compressed)} — padding/truncating")
        compressed = (compressed + [""] * len(lines))[: len(lines)]
    return compressed


def _reassemble(original_lines, compressed_messages):
    """Graft compressed messages onto original timestamp+level prefixes."""
    out = []
    for line, msg in zip(original_lines, compressed_messages):
        parts = line.split('] ', 2)
        out.append(parts[0] + '] ' + parts[1] + '] ' + msg if len(parts) == 3 else line)
    return out


# --- Tools ---

def get_log_levels():
    lines = _fetch_log_lines()
    text = "\n".join(lines)
    levels = sorted(set(re.findall(r'\[(\w+)\]', text)))
    return json.dumps({"levels": levels, "count": {l: text.count(f"[{l}]") for l in levels}})


def filter_logs(levels):
    matched = [l for l in _fetch_log_lines() if any(f"[{lvl}]" in l for lvl in levels)]
    return json.dumps({"matched_lines": len(matched), "levels": levels, "preview": "\n".join(matched[:3])})


def prepare_submission(levels, deduplicate=False):
    global _prepared
    matched = [_compact_timestamp(l) for l in _fetch_log_lines() if any(f"[{lvl}]" in l for lvl in levels)]
    if deduplicate:
        matched = _dedup_by_message(matched)

    chunks = [matched[i: i + CHUNK_SIZE] for i in range(0, len(matched), CHUNK_SIZE)]
    logger.info(f"Compressing {len(matched)} lines across {len(chunks)} chunk(s)...")

    compressed = []
    for i, chunk in enumerate(chunks):
        logger.info(f"  chunk {i + 1}/{len(chunks)} ({len(chunk)} lines)")
        compressed.extend(_reassemble(chunk, _compress_chunk(chunk)))

    _prepared = "\n".join(compressed)
    enc = tiktoken.encoding_for_model("gpt-4o")
    token_count = len(enc.encode(_prepared))
    return json.dumps({"lines": len(compressed), "token_count": token_count, "preview": "\n".join(compressed[:3])})


def submit_answer(logs=None):
    import os
    from datetime import datetime
    from common import ApiError

    if not logs:
        if not _prepared:
            return json.dumps({"status": "error", "message": "Nothing prepared. Call prepare_submission first."})
        logs = _prepared

    submissions_dir = os.path.join(os.path.dirname(__file__), "submissions")
    os.makedirs(submissions_dir, exist_ok=True)
    path = os.path.join(submissions_dir, datetime.now().strftime("%Y%m%d_%H%M%S") + "_alt.json")

    try:
        result = submit(api_key=API_KEY, task="failure", answer={"logs": logs})
        outcome = {"status": "ok", "code": result.status, "response": dict(result)}
    except ApiError as e:
        outcome = {"status": "error", "code": e.code, "response": e.body, "submitted": logs[:200]}

    with open(path, "w") as f:
        json.dump({"request": {"task": "failure", "answer": {"logs": logs}}, "response": outcome}, f, indent=2)
    logger.info(f"Submission saved to {path}")
    return json.dumps(outcome)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_log_levels",
            "description": "List available log levels and their line counts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_logs",
            "description": "Count lines matching the given levels and return a 3-line preview. Use for exploration only.",
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
            "name": "prepare_submission",
            "description": (
                "Filter logs by level, compact timestamps, optionally deduplicate by message text, "
                "then compress message text chunk-by-chunk via a structured LLM call. "
                "Returns exact token count and a 3-line preview. Target: under 1500 tokens. "
                "Tip: deduplicate=true reduces CRIT+ERRO from ~396 to ~36 lines before compression."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "levels": {"type": "array", "items": {"type": "string"}, "description": "Log levels to include"},
                    "deduplicate": {"type": "boolean", "description": "Remove duplicate messages before compressing"},
                },
                "required": ["levels"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": "Submit the prepared logs. Call with no arguments to use the prepare_submission result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "logs": {"type": "string", "description": "Optional override string."},
                },
            },
        },
    },
]

TOOL_HANDLERS = {
    "get_log_levels": get_log_levels,
    "filter_logs": filter_logs,
    "prepare_submission": prepare_submission,
    "submit_answer": submit_answer,
}

GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def on_iteration(i, max_iterations):
    logger.info(f"{CYAN}[iteration {i + 1}/{max_iterations}]{RESET}")


def on_tool_call(name, args, result):
    lines = result.splitlines()
    preview = "\n    ".join(lines[:3])
    suffix = f"\n    ... ({len(lines)} lines total)" if len(lines) > 3 else ""
    logger.info(f"{YELLOW}← {name}:\n    {preview}{suffix}{RESET}")


def chat():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input(f"\n{GREEN}You: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            print(cost_tracker.summary())
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print(cost_tracker.summary())
            break

        messages.append({"role": "user", "content": user_input})
        pre_run_len = len(messages)

        def make_handler(name, fn):
            def wrapped(**kwargs):
                logger.info(f"{YELLOW}→ {name}({json.dumps(kwargs)}){RESET}")
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
                tools=TOOLS,
                tool_handlers=instrumented,
                on_tool_call=on_tool_call,
                on_iteration=on_iteration,
                max_iterations=20,
            )
        except KeyboardInterrupt:
            messages = messages[:pre_run_len - 1]
            print(f"\n{YELLOW}[Interrupted — back to prompt]{RESET}")
            continue

        if answer:
            print(f"\n{CYAN}Assistant:{RESET} {answer}")
        else:
            print("\n[No response — max iterations reached]")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    chat()
