import re
import json
import sys
from common import api_get, get_api_key, submit
from endpoints import DATA_FAILURE

API_KEY = get_api_key()

LEVELS = {"CRIT", "ERRO"}


def fetch_lines():
    return api_get(DATA_FAILURE.format(api_key=API_KEY), "text").splitlines()


def compact_timestamp(line):
    return re.sub(r'\[(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):\d{2}\]', r'[\1 \2:\3]', line)


def dedup_by_message(lines):
    seen, out = set(), []
    for l in lines:
        msg = l.split('] ', 2)[-1]
        if msg not in seen:
            out.append(l)
            seen.add(msg)
    return out


def build_payload():
    lines = fetch_lines()
    matched = [compact_timestamp(l) for l in lines if any(f"[{lvl}]" in l for lvl in LEVELS)]
    return "\n".join(dedup_by_message(matched))


def main():
    payload = build_payload()
    line_count = payload.count('\n') + 1
    print(f"Submitting {line_count} lines...")
    result = submit(api_key=API_KEY, task="failure", answer={"logs": payload})
    print(json.dumps(dict(result), indent=2))


if __name__ == "__main__":
    main()
