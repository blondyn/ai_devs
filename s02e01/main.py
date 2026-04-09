import json
import os
import sys

from common import get_api_key, api_get, submit, ApiError
from endpoints import DATA_CATEGORIES

API_KEY = get_api_key()
RESULTS_FILE = os.path.join(os.path.dirname(__file__), "results.json")

CUSTOM_ITEMS = [
    # {"code": "x001", "description": "A shiny red apple"},
]

PROMPTS = {
    "default": """Classify as DNG or NEU.
DNG: only weapons, explosives, poison.
NEU: everything else including reactor items and machinery.
One word answer: DNG or NEU

Item: {identifier}
""",
    "verbose": """Classify as DNG or NEU.
DNG: only weapons, explosives, poison.
NEU: everything else including reactor items and machinery.
One word answer: DNG or NEU

Item: {identifier}
""",
}

ACTIVE_PROMPT = "verbose"


def load_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_results(results):
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def row_key(row):
    """Generate a unique key for a row based on its content."""
    return json.dumps(row, sort_keys=True)


def build_prompt(identifier: str) -> str:
    """Build classification prompt using the active prompt template."""
    return PROMPTS[ACTIVE_PROMPT].format(identifier=identifier)


def reset_balance():
    """Reset the API balance."""
    result = submit(API_KEY, task="categorize", answer={"prompt": "reset"})
    print(f"Balance reset: {result.get('balance', 'unknown')}")


def fetch_rows():
    """Fetch rows from API."""
    path = DATA_CATEGORIES.format(api_key=API_KEY)
    return api_get(path, "csv")


def retry(attempts_left):
    """Reset balance and return True if retries remain, False otherwise."""
    if attempts_left <= 0:
        return False
    reset_balance()
    return True


def main():
    """Main entry point."""
    reset_balance()
    rows = CUSTOM_ITEMS if CUSTOM_ITEMS else fetch_rows()
    results = load_results()

    try:
        for row in rows:
            key = row_key(row)
            identifier = row.get("identifier", str(row))
            prompt = {"prompt": build_prompt(identifier)}
            attempts_left = 3

            while True:
                try:
                    result = submit(API_KEY, task="categorize", answer=prompt)
                    break
                except ApiError as e:
                    if e.code == 400:
                        attempts_left -= 1
                        if not retry(attempts_left):
                            sys.exit(f"Max retries reached for {identifier}, exiting.")
                        print(f"Balance reset, retrying ({attempts_left} attempts left)...")
                    else:
                        raise

            results[key] = {"input": row, "response": result}
            print(f"Processed: {row}")
            print(f"Response: {result}\n")
    finally:
        save_results(results)

    print(f"\nCompleted. Processed {len(results)} items.")


if __name__ == "__main__":
    main()
