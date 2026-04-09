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
    "default": "Categorize the following item as DNG (dangerous: weapons, explosives, poison) or NEU (neutral: everything else, including all reactor-related items). The output should be exactly one word. Consider carefully. Do not output any preamble or postamble. Output DNG or NEU only. {identifier}",
}

ACTIVE_PROMPT = "default"


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


def run(prompt_template=None, items=None):
    """Run classification with given prompt template and items.

    Returns list of result dicts with debug info from each API response.
    Raises on non-retryable errors.
    """
    reset_balance()
    if prompt_template is None:
        prompt_template = PROMPTS[ACTIVE_PROMPT]
    rows = items if items else (CUSTOM_ITEMS if CUSTOM_ITEMS else fetch_rows())
    results = []

    for row in rows:
        code = row.get("code", "")
        desc = row.get("description", str(row))
        identifier = f"{code}: {desc}" if code else desc
        prompt = {"prompt": prompt_template.format(identifier=identifier)}
        attempts_left = 3

        while True:
            try:
                result = submit(API_KEY, task="categorize", answer=prompt)
                break
            except ApiError as e:
                print(f"  API error {e.code}: {e.body}")
                if e.code == 402:
                    attempts_left -= 1
                    if not retry(attempts_left):
                        print(f"Max retries reached for {identifier}, stopping.")
                        return results
                    print(f"Balance reset, retrying ({attempts_left} attempts left)...")
                else:
                    print(f"Error HTTP {e.code} for {identifier}, stopping.")
                    return results
            except Exception as e:
                print(f"  Unexpected error: {e}, stopping.")
                return results

        debug = result.get("debug", {})
        results.append({
            "identifier": identifier,
            "output": debug.get("output"),
            "tokens": debug.get("tokens", 0),
            "cached_tokens": debug.get("cached_tokens", 0),
            "flag": debug.get("flag"),
            "result": debug.get("result"),
        })
        print(f"  [{len(results)}/{len(rows)}] {identifier[:50]} -> {debug.get('output')} "
              f"(tokens: {debug.get('tokens')}, cached: {debug.get('cached_tokens')})")

    return results


def main():
    """Main entry point."""
    results = run()
    flag = next((r["flag"] for r in results if r["flag"]), None)
    if flag:
        print(f"\nFlag: {flag}")
    print(f"Completed. Processed {len(results)} items.")


if __name__ == "__main__":
    main()
