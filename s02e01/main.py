import json
import os

from common import get_api_key, api_get, submit, ApiError
from endpoints import DATA_CATEGORIES

API_KEY = get_api_key()
RESULTS_FILE = os.path.join(os.path.dirname(__file__), "results.json")


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


def build_prompt(idenfier: str) -> str:
    """Build classification prompt for LLM."""
    return f"""Classify item as DNG or NEU.

Treat as NEU only if:
- Item is harmless and poses no danger, OR
- Item is related to reactor elements


Reply: DNG or NEU


Item: {idenfier}
"""


def main():
    """Main entry point."""
    path = DATA_CATEGORIES.format(api_key=API_KEY)
    rows = api_get(path, "csv")
    results = load_results()

    try:
        for row in rows:
            key = row_key(row)

            # if key in results:
            #     print(f"Skipping (already processed): {row}")
            #     continue

            idenfier = row.get("identifier", str(row))
            prompt = {"prompt": build_prompt(idenfier)}

            try:
                result = submit(API_KEY, task="categorize", answer=prompt)
            except ApiError as e:
                print(f"Failed to process: {row}")
                print(f"API error: HTTP {e.code} - {e.body}\n")
                break

            results[key] = {"input": row, "response": result}
            print(f"Processed: {row}")
            print(f"Response: {result}\n")
    finally:
        save_results(results)

    print(f"\nCompleted. Processed {len(results)} items.")


if __name__ == "__main__":
    main()

