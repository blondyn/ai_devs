import json
import os
import re
import sys
import time
from collections import Counter

import tiktoken
from common import api_get, get_api_key, submit, llm, cost_tracker, ApiError
from endpoints import DATA_FAILURE

API_KEY = get_api_key()
TOKEN_LIMIT = 1500
CHUNK_SIZE = 50

COMPRESSION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "compressed_chunk",
        "schema": {
            "type": "object",
            "properties": {
                "messages": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["messages"],
            "additionalProperties": False,
        },
    },
}

GREEN  = "\033[32m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
RED    = "\033[31m"
RESET  = "\033[0m"


# --- pipeline steps ---

def step_download():
    print(f"{CYAN}[1] Downloading failure log...{RESET}")
    lines = api_get(DATA_FAILURE.format(api_key=API_KEY), "text").splitlines()
    print(f"    {len(lines)} lines fetched.")
    return lines


def step_dedup_stats(lines):
    print(f"\n{CYAN}[2] Analysing and deduplicating...{RESET}")
    level_re = re.compile(r'\[([A-Z]+)\]')

    def extract_level(line):
        m = level_re.search(line)
        return m.group(1) if m else "OTHER"

    def extract_message(line):
        parts = line.split('] ', 2)
        return parts[2] if len(parts) == 3 else line

    before = Counter(extract_level(l) for l in lines)

    seen, deduped = set(), []
    for l in lines:
        msg = extract_message(l)
        if msg not in seen:
            deduped.append(l)
            seen.add(msg)

    after = Counter(extract_level(l) for l in deduped)
    all_levels = sorted(before.keys() | after.keys())

    print(f"\n    {'Level':<8} {'Before':>8} {'After':>8} {'Removed':>9}")
    print(f"    {'-'*8} {'-'*8} {'-'*8} {'-'*9}")
    for lvl in all_levels:
        b, a = before[lvl], after[lvl]
        print(f"    {lvl:<8} {b:>8} {a:>8} {b-a:>9}")
    print(f"    {'TOTAL':<8} {sum(before.values()):>8} {sum(after.values()):>8} {sum(before.values())-sum(after.values()):>9}")

    return deduped, all_levels


def step_select_levels(deduped, all_levels):
    print(f"\n{CYAN}[3] Select log levels to include{RESET}")
    print(f"    Available: {', '.join(all_levels)}")
    print(f"    Press Enter to include all, or enter comma-separated levels (e.g. CRIT,ERRO,WARN):")
    raw = input(f"    {GREEN}>{RESET} ").strip()
    if not raw:
        chosen = all_levels
    else:
        chosen = [l.strip().upper() for l in raw.split(",") if l.strip()]
        invalid = [l for l in chosen if l not in all_levels]
        if invalid:
            print(f"    {YELLOW}Unknown levels ignored: {invalid}{RESET}")
            chosen = [l for l in chosen if l in all_levels]
    filtered = [l for l in deduped if any(f"[{lvl}]" in l for lvl in chosen)]
    print(f"    {len(filtered)} lines selected ({', '.join(chosen)}).")
    return filtered, chosen


def step_compact_timestamps(lines):
    def compact(line):
        return re.sub(r'\[(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):\d{2}\]', r'[\1 \2:\3]', line)
    return [compact(l) for l in lines]


def step_compress(lines):
    print(f"\n{CYAN}[4] Compressing messages via LLM...{RESET}")
    chunks = [lines[i: i + CHUNK_SIZE] for i in range(0, len(lines), CHUNK_SIZE)]
    compressed = []
    for i, chunk in enumerate(chunks):
        print(f"    chunk {i + 1}/{len(chunks)} ({len(chunk)} lines)", end="", flush=True)
        msgs = _compress_chunk(chunk)
        compressed.extend(_reassemble(chunk, msgs))
        print(f" → done")
    return compressed


def _compress_chunk(lines):
    messages = [
        {
            "role": "system",
            "content": (
                f"Shorten each log message to 3-5 words. "
                f"Return exactly {len(lines)} strings in the same order as input. "
                "Always keep uppercase identifiers (component names like ECCS8, WTRPMP, STMTURB12, WTANK07, FIRMWARE, PWR01). "
                "Drop the log level word if it appears in the message text. "
                "Keep the failure mode or action. "
                "No trailing punctuation — do not end messages with a period or comma. "
                "Drop boilerplate endings like 'is required', 'are required', 'is terminated'."
            ),
        },
        {"role": "user", "content": "\n".join(lines)},
    ]
    result = llm(messages, schema=COMPRESSION_SCHEMA, max_tokens=1024)
    msgs = result.get("messages", [])
    if len(msgs) != len(lines):
        msgs = (msgs + [""] * len(lines))[: len(lines)]
    return msgs


def _reassemble(original, compressed_messages):
    out = []
    for line, msg in zip(original, compressed_messages):
        parts = line.split('] ', 2)
        out.append(parts[0] + '] ' + parts[1] + '] ' + msg if len(parts) == 3 else line)
    return out


def count_tokens(text):
    enc = tiktoken.encoding_for_model("gpt-4o")
    return len(enc.encode(text))


def step_token_check(lines):
    text = "\n".join(lines)
    tokens = count_tokens(text)
    status = f"{GREEN}✓{RESET}" if tokens <= TOKEN_LIMIT else f"{RED}✗{RESET}"
    print(f"\n{CYAN}[5] Token check:{RESET} {tokens}/{TOKEN_LIMIT} {status}")
    return text, tokens


def _save_submission(text, response):
    from datetime import datetime
    submissions_dir = os.path.join(os.path.dirname(__file__), "submissions")
    os.makedirs(submissions_dir, exist_ok=True)
    path = os.path.join(submissions_dir, datetime.now().strftime("%Y%m%d_%H%M%S") + "_workflow.json")
    with open(path, "w") as f:
        json.dump({"request": {"task": "failure", "answer": {"logs": text}}, "response": response}, f, indent=2)
    print(f"    Saved to {path}")


def step_submit(text):
    print(f"\n{CYAN}[6] Submitting...{RESET}")
    try:
        result = submit(api_key=API_KEY, task="failure", answer={"logs": text})
        response = dict(result)
    except ApiError as e:
        response = {"error": True, "code": e.code, "body": e.body}
    _save_submission(text, response)
    return response


def step_handle_response(response):
    body = json.dumps(response, indent=2)
    if "{FLG:" in body:
        flag = re.search(r'\{FLG:[^}]+\}', body)
        print(f"\n{GREEN}FLAG: {flag.group(0)}{RESET}")
        return True
    print(f"\n{YELLOW}Server response:{RESET}\n{body}")
    return False


def step_ask_user(lines, chosen_levels, all_levels):
    print(f"\n{CYAN}What would you like to do?{RESET}")
    print("  levels <CRIT,ERRO,...>  — change included levels")
    print("  compress                — re-compress with shorter messages")
    print("  submit                  — submit current content as-is")
    print("  quit                    — exit")
    while True:
        cmd = input(f"\n{GREEN}>{RESET} ").strip().lower()
        if cmd == "quit":
            return None, None, False
        if cmd == "submit":
            return lines, chosen_levels, True
        if cmd == "compress":
            return lines, chosen_levels, "compress"
        if cmd.startswith("levels "):
            raw = cmd[7:].upper()
            new_levels = [l.strip() for l in raw.split(",") if l.strip() in all_levels]
            if not new_levels:
                print(f"  {YELLOW}No valid levels. Available: {', '.join(all_levels)}{RESET}")
                continue
            return lines, new_levels, "refilter"
        print(f"  Unknown command.")


# --- main pipeline ---

def run():
    # 1. Download
    raw_lines = step_download()

    # 2. Dedup + stats
    deduped, all_levels = step_dedup_stats(raw_lines)

    # 3. Level selection
    selected, chosen = step_select_levels(deduped, all_levels)
    selected = step_compact_timestamps(selected)

    # 4. Compress
    compressed = step_compress(selected)

    while True:
        # 5. Token check
        text, tokens = step_token_check(compressed)

        if tokens > TOKEN_LIMIT:
            print(f"    {YELLOW}Over limit. Consider fewer levels or re-compressing.{RESET}")

        # 6. Submit
        response = step_submit(text)

        # 7. Check result
        if step_handle_response(response):
            break

        # 8. Ask what to do next
        compressed, chosen, action = step_ask_user(compressed, chosen, all_levels)
        if action is None:
            print("Bye!")
            break
        if action == "refilter":
            selected = [l for l in deduped if any(f"[{lvl}]" in l for lvl in chosen)]
            selected = step_compact_timestamps(selected)
            compressed = step_compress(selected)
        if action == "compress":
            compressed = step_compress(compressed)

    print(f"\n{cost_tracker.summary()}")


if __name__ == "__main__":
    run()
