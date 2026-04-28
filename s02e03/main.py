import json
import logging

import tiktoken
from common import api_get, interactive_agent_loop, get_api_key, submit, pause_spinner, resume_spinner, cost_tracker
from endpoints import DATA_FAILURE

logger = logging.getLogger(__name__)

API_KEY = get_api_key()

SYSTEM_PROMPT = """You are a failure-log analysis assistant. You have access to tools for fetching, filtering, and submitting logs.

Rules for every response:
1. NEVER paste raw log lines into your reply. Instead summarise what the tool returned: state how many lines matched, what log levels were present, and one or two representative patterns you noticed.
2. After reporting facts, interpret what they mean — e.g. "3 consecutive CRITICAL errors from the database module suggest connection pool exhaustion."
3. Always end with a concrete next step: a specific tool call you recommend next, or a hypothesis to test.
4. Keep replies concise — a few sentences of summary, one sentence of interpretation, one sentence of suggestion.
5. Always wait for the instructions. You can suggest what you want to do next, but ask for permission.

Submission workflows (pick one):

Quick path — Python handles everything:
- Call prepare_submission with the desired levels and optionally max_message_words to truncate messages.
- prepare_submission returns an exact token count and a 3-line preview. Target is under 1500 tokens.
- If over 1500 tokens: use deduplicate=True (CRIT+ERRO deduped ≈ 36 lines / 1250 tokens), or reduce to CRIT only.
- Call submit_answer with no arguments once under 1500 tokens.

Compressed path — shorter messages, fewer tokens:
- Call clear_chunks to reset the store.
- Call get_chunk(levels, 0) to get the first 50-line slice. Compress the message text of each line (keep [YYYY-MM-DD H:00] [LEVEL] prefix intact), then call store_chunk with the compressed lines.
- Repeat get_chunk / store_chunk for chunk_index 1, 2, … until chunk_index == total_chunks - 1.
- Call submit_answer with no arguments — it assembles all stored chunks.

Only submit lines that are actual log entries. Never submit summaries, free text, or invented content.
"""


def count_tokens(text, model="gpt-4o"):
    """Count tokens in text using tiktoken."""
    enc = tiktoken.encoding_for_model(model)
    count = len(enc.encode(text))
    return json.dumps({"token_count": count, "model": model, "text_length": len(text)})

import re

_log_lines = None
_prepared = None
_prepared_chunks = []

def _fetch_log_lines():
    global _log_lines
    if _log_lines is None:
        _log_lines = api_get(DATA_FAILURE.format(api_key=API_KEY), "text").splitlines()
    return _log_lines

def _compact_timestamp(line):
    return re.sub(r'\[(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):\d{2}\]', r'[\1 \2:\3]', line)

def _truncate_message(line, max_words):
    parts = line.split('] ', 2)
    if len(parts) == 3:
        words = parts[2].split()[:max_words]
        return parts[0] + '] ' + parts[1] + '] ' + ' '.join(words)
    return line

def _dedup_by_message(lines):
    seen, out = set(), []
    for l in lines:
        msg = l.split('] ', 2)[-1]
        if msg not in seen:
            out.append(l)
            seen.add(msg)
    return out

def prepare_submission(levels, max_message_words=None, deduplicate=False):
    """Filter logs by level, compact timestamps, optionally truncate/dedup, and store for submission."""
    global _prepared
    matched = [_compact_timestamp(l) for l in _fetch_log_lines() if any(f"[{lvl}]" in l for lvl in levels)]
    if deduplicate:
        matched = _dedup_by_message(matched)
    if max_message_words:
        matched = [_truncate_message(l, max_message_words) for l in matched]
    _prepared = "\n".join(matched)
    preview = "\n".join(matched[:3])
    enc = tiktoken.encoding_for_model("gpt-4o")
    token_count = len(enc.encode(_prepared))
    return json.dumps({"lines": len(matched), "token_count": token_count, "preview": preview})

def get_chunk(levels, chunk_index, chunk_size=50):
    """Return a slice of filtered+compacted log lines for LLM compression."""
    matched = [_compact_timestamp(l) for l in _fetch_log_lines() if any(f"[{lvl}]" in l for lvl in levels)]
    total_chunks = (len(matched) + chunk_size - 1) // chunk_size
    start = chunk_index * chunk_size
    chunk = matched[start:start + chunk_size]
    return json.dumps({"chunk_index": chunk_index, "total_chunks": total_chunks,
                        "lines_in_chunk": len(chunk), "lines": "\n".join(chunk)})

def store_chunk(lines):
    """Append compressed lines to the chunk store."""
    global _prepared_chunks
    _prepared_chunks.append(lines)
    return json.dumps({"stored_chunks": len(_prepared_chunks)})

def clear_chunks():
    """Clear the chunk store to start fresh."""
    global _prepared_chunks
    _prepared_chunks = []
    return json.dumps({"status": "cleared"})

def get_failure_log():
    """Return total line count of the failure log."""
    return json.dumps({"total_lines": len(_fetch_log_lines())})

def filter_logs(levels):
    """Return count and 3-line preview of lines matching the specified levels."""
    matched = [l for l in _fetch_log_lines() if any(f"[{lvl}]" in l for lvl in levels)]
    preview = "\n".join(matched[:3])
    return json.dumps({"matched_lines": len(matched), "levels": levels, "preview": preview})

def search_logs(query):
    """Return count and 3-line preview of lines containing the query string (case-insensitive)."""
    q = query.lower()
    matched = [l for l in _fetch_log_lines() if q in l.lower()]
    preview = "\n".join(matched[:3])
    return json.dumps({"matched_lines": len(matched), "query": query, "preview": preview})

def submit_answer(logs=None):
    """Submit the answer. Uses prepare_submission result if logs is omitted."""
    import os
    from datetime import datetime
    from common import ApiError
    if not logs:
        if _prepared_chunks:
            logs = "\n".join(_prepared_chunks)
        elif _prepared:
            logs = _prepared
        else:
            return json.dumps({"status": "error", "message": "Nothing prepared. Call prepare_submission or store_chunk first."})

    submissions_dir = os.path.join(os.path.dirname(__file__), "submissions")
    os.makedirs(submissions_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        result = submit(api_key=API_KEY, task="failure", answer={"logs": logs})
        outcome = {"status": "ok", "code": result.status, "response": dict(result)}
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
            "description": "Return the total line count of the failure log. Use this to learn how many lines exist before filtering.",
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
            "description": "Count lines matching one or more log levels (e.g. ['CRIT','ERRO']) and return a 3-line preview. Use this to explore the data — not to build submission content. To prepare submission content, use prepare_submission or get_chunk instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "levels": {"type": "array", "items": {"type": "string"}, "description": "Log levels to filter by (exact match on [LEVEL] token)"},
                },
                "required": ["levels"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_logs",
            "description": "Count lines containing a substring (case-insensitive) and return a 3-line preview. Use this to explore specific components or keywords — not to build submission content.",
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
            "name": "prepare_submission",
            "description": "Filter logs by level, compact timestamps to [YYYY-MM-DD HH:MM] format, optionally truncate each message to N words, and store for submission. Returns exact tiktoken count and a 3-line preview. The target is under 1500 tokens. Call submit_answer with no arguments afterwards.",
            "parameters": {
                "type": "object",
                "properties": {
                    "levels": {"type": "array", "items": {"type": "string"}, "description": "Log levels to include"},
                    "max_message_words": {"type": "integer", "description": "If set, truncate each log message to this many words."},
                    "deduplicate": {"type": "boolean", "description": "If true, keep only the first occurrence of each unique message text. CRIT+ERRO deduped = ~36 lines / ~1250 tokens."},
                },
                "required": ["levels"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chunk",
            "description": "Return a slice of filtered+timestamp-compacted log lines for you to compress. Call repeatedly with increasing chunk_index until chunk_index == total_chunks - 1. After compressing each chunk, call store_chunk with your compressed version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "levels": {"type": "array", "items": {"type": "string"}, "description": "Log levels to include"},
                    "chunk_index": {"type": "integer", "description": "Zero-based chunk index"},
                    "chunk_size": {"type": "integer", "description": "Lines per chunk (default 50)", "default": 50},
                },
                "required": ["levels", "chunk_index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "store_chunk",
            "description": "Append your compressed version of a chunk to the submission store. Call after compressing each chunk from get_chunk. Rules: keep the [YYYY-MM-DD HH:MM] [LEVEL] prefix on every line unchanged; preserve the exact line order; you may only shorten the message text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lines": {"type": "string", "description": "Compressed log lines (newline-separated) to store"},
                },
                "required": ["lines"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_chunks",
            "description": "Clear the chunk store so you can start a fresh compression pass.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": "Submit the prepared log. Call with no arguments to submit whatever prepare_submission stored, or pass a custom logs string to override.",
            "parameters": {
                "type": "object",
                "properties": {
                    "logs": {"type": "string", "description": "Optional override. If omitted, submits the prepare_submission result."},
                },
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
    "prepare_submission": prepare_submission,
    "get_chunk": get_chunk,
    "store_chunk": store_chunk,
    "clear_chunks": clear_chunks,
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
                max_iterations=30,
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
