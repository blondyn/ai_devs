import json
import sys
import os
from datetime import datetime
from string import Template

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import llm
from s02e01.main import run, fetch_rows

RUNS_FILE = os.path.join(os.path.dirname(__file__), "runs.json")

META_PROMPT = Template("""You are a prompt engineer optimizing a classification prompt.

The prompt classifies items as DNG (dangerous) or NEU (neutral).
Rules the prompt must enforce:
- DNG: only weapons, explosives, poison
- NEU: everything else, INCLUDING all reactor-related items and machinery
- Output must be exactly one word: DNG or NEU

The prompt contains a variable {identifier} where the item description goes.
The variable part "{identifier}" does NOT count toward the token limit.

Optimization goals (in priority order):
1. Correctness: all items must be classified correctly
2. Cacheability: the static part before {identifier} MUST be at least 40 tokens long so the LLM can cache it. Put {identifier} at the very end.
3. Brevity: minimize total tokens while maintaining correctness. Aim for 50-80 total tokens.

Here are the items that will be classified:
$items

$feedback

Generate ONLY the prompt template. Include {identifier} exactly once as the placeholder.
Do not include any explanation or commentary.""")

MAX_ITERATIONS = 10


def format_items(rows):
    return "\n".join(f"- {r.get('identifier', str(r))}" for r in rows)


def load_runs():
    if os.path.exists(RUNS_FILE):
        with open(RUNS_FILE, "r") as f:
            return json.load(f)
    return []


def save_run(run_data):
    runs = load_runs()
    runs.append(run_data)
    with open(RUNS_FILE, "w") as f:
        json.dump(runs, f, indent=2, ensure_ascii=False)


def analyze_results(results):
    total_tokens = sum(r["tokens"] for r in results)
    total_cached = sum(r["cached_tokens"] for r in results)
    wrong = [r for r in results if r["result"] != "correct classification"]
    flag = next((r["flag"] for r in results if r["flag"]), None)
    cache_rate = (total_cached / total_tokens * 100) if total_tokens else 0
    return {
        "total_tokens": total_tokens,
        "total_cached": total_cached,
        "cache_rate": cache_rate,
        "wrong": wrong,
        "flag": flag,
        "avg_tokens": total_tokens / len(results) if results else 0,
    }



def build_feedback(history):
    """Build feedback from previous runs for the LLM."""
    if not history:
        return "This is the first attempt. Start with a concise prompt."

    lines = ["Previous attempts (learn from these):"]
    for h in history:
        status = "PASS" if h["wrong_count"] == 0 else f"FAIL ({h['wrong_count']} wrong)"
        lines.append(
            f"  [{status}] avg_tokens={h['avg_tokens']:.0f}, "
            f"cache_rate={h['cache_rate']:.1f}%, "
            f"prompt: {h['prompt'][:100]}..."
        )
        if h.get("wrong_details"):
            for w in h["wrong_details"]:
                lines.append(f"    WRONG: '{w['identifier']}' -> {w['output']}")

    best = min(
        [h for h in history if h["wrong_count"] == 0],
        key=lambda h: (-h["cache_rate"], h["avg_tokens"]),
        default=None,
    )
    if best:
        lines.append(f"\nBest so far: {best['avg_tokens']:.0f} avg tokens, {best['cache_rate']:.1f}% cache rate.")
        lines.append("Try to beat it: higher cache rate OR same cache rate with fewer tokens.")
        lines.append("Try a DIFFERENT structure or wording. Do NOT repeat previous prompts.")
    else:
        lines.append("\nNo correct prompt yet. Focus on correctness first.")

    return "\n".join(lines)


def main():
    rows = fetch_rows()
    items_str = format_items(rows)
    history = []
    best = None

    for i in range(MAX_ITERATIONS):
        print(f"\n{'='*60}")
        print(f"Iteration {i + 1}/{MAX_ITERATIONS}")
        print(f"{'='*60}")

        feedback = build_feedback(history)
        prompt_template = llm(
            [{"role": "user", "content": META_PROMPT.substitute(items=items_str, feedback=feedback)}],
            max_tokens=512,
            temperature=0.9,
        ).strip()

        print(f"\nPrompt:\n---\n{prompt_template}\n---")

        results = run(prompt_template=prompt_template, items=rows)
        if not results:
            print("No results returned, skipping.\n")
            continue

        stats = analyze_results(results)

        print(f"\nStats: {stats['avg_tokens']:.0f} avg tokens, "
              f"{stats['cache_rate']:.1f}% cache rate, "
              f"{len(stats['wrong'])} wrong")

        run_entry = {
            "timestamp": datetime.now().isoformat(),
            "iteration": i + 1,
            "model": os.environ.get("LLM_MODEL", "google/gemini-2.0-flash-001"),
            "prompt": prompt_template,
            "total_tokens": stats["total_tokens"],
            "total_cached": stats["total_cached"],
            "cache_rate": round(stats["cache_rate"], 2),
            "avg_tokens": round(stats["avg_tokens"], 1),
            "wrong_count": len(stats["wrong"]),
            "wrong_details": [{"identifier": w["identifier"], "output": w["output"]} for w in stats["wrong"]],
            "flag": stats["flag"],
        }
        history.append(run_entry)

        if not stats["flag"]:
            print("No flag returned, prompt incomplete — skipping.\n")
            continue

        save_run(run_entry)
        print(f"Flag: {stats['flag']}")

        if best is None or stats["cache_rate"] > best["cache_rate"] \
                or (stats["cache_rate"] == best["cache_rate"]
                    and stats["avg_tokens"] < best["avg_tokens"]):
            best = {**stats, "prompt": prompt_template, "iteration": i + 1}
            print("^ New best!")

        print()

    if best:
        print(f"{'='*60}")
        print(f"BEST PROMPT (iteration {best['iteration']}):")
        print(f"---\n{best['prompt']}\n---")
        print(f"Avg tokens: {best['avg_tokens']:.0f}, Cache rate: {best['cache_rate']:.1f}%")
        if best.get("flag"):
            print(f"Flag: {best['flag']}")
    else:
        print("\nNo successful run found.")


if __name__ == "__main__":
    main()
