import io
import json
import os

from PIL import Image, ImageDraw

from common import llm_vision_call, llm
from s02e02.main import (
    open_image, to_png_bytes, to_b64, preprocess, load_png,
    CELL_SCHEMA, PROMPT_ASCII, OUTPUT_DIR,
)

SOLUTION_FILE = os.path.join(os.path.dirname(__file__), "solution.json")
GRID_IMAGE = os.path.join(OUTPUT_DIR, "grid_only.png")
MAX_ITERATIONS = 10

PROMPT_IMPROVE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "improved_prompt",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
}


def draw_reference(letter, rotation, size=100, line_width=6):
    """Generate a reference image for a letter at a given rotation."""
    img = Image.new("1", (size, size), 1)  # white background
    draw = ImageDraw.Draw(img)
    mid = size // 2

    # Draw segments based on letter type at 0° then rotate
    # At 0°: I=vertical, L=arms right+up, T=top bar + stem down
    if letter == "I":
        # vertical line
        draw.line([(mid, 0), (mid, size)], fill=0, width=line_width)
    elif letter == "L":
        # arm up + arm right
        draw.line([(mid, 0), (mid, mid)], fill=0, width=line_width)
        draw.line([(mid, mid), (size, mid)], fill=0, width=line_width)
    elif letter == "T":
        # horizontal top bar + stem down
        draw.line([(0, mid), (size, mid)], fill=0, width=line_width)
        draw.line([(mid, mid), (mid, size)], fill=0, width=line_width)

    # Rotate by the specified angle
    if rotation:
        img = img.rotate(-rotation, expand=False)  # negative = clockwise

    return to_png_bytes(img)


def generate_all_references():
    """Generate reference images for all letter+rotation combos."""
    refs = {}
    for letter in ["I", "L", "T"]:
        for rotation in [0, 90, 180, 270]:
            refs[(letter, rotation)] = draw_reference(letter, rotation)
    return refs


def load_solution():
    with open(SOLUTION_FILE) as f:
        return json.load(f)


def split_and_preprocess(grid_data):
    """Split grid_only image into 3x3 preprocessed cells."""
    img = open_image(grid_data)
    w, h = img.size
    cell_w, cell_h = w // 3, h // 3
    cells = []
    for r in range(3):
        row = []
        for c in range(3):
            box = (c * cell_w, r * cell_h, (c + 1) * cell_w, (r + 1) * cell_h)
            cell = preprocess(to_png_bytes(img.crop(box)))
            row.append(cell)
        cells.append(row)
    return cells


def classify_cell(cell_data, prompt, model=None):
    """Send a single cell to LLM for classification."""
    kwargs = {"schema": CELL_SCHEMA}
    if model:
        kwargs["model"] = model
    return llm_vision_call([
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{to_b64(cell_data)}"}},
            {"type": "text", "text": prompt},
        ]}
    ], **kwargs)


def evaluate(cells, solution, prompt):
    """Classify all cells and compare to solution. Return (results, failures)."""
    results = []
    failures = []
    for r in range(3):
        row = []
        for c in range(3):
            result = classify_cell(cells[r][c], prompt)
            expected = solution[r][c]
            match = result["letter"] == expected["letter"] and result["rotation"] == expected["rotation"]
            row.append(result)
            if not match:
                failures.append({
                    "row": r, "col": c,
                    "expected": expected,
                    "got": result,
                    "cell_image": cells[r][c],
                })
        results.append(row)
    return results, failures


def improve_prompt(current_prompt, failures, refs):
    """Ask LLM to improve the prompt, showing PIL-generated references and misclassified cells."""
    content = [
        {"type": "text", "text": f"""You are a prompt engineer. The following prompt is used to classify pipe segments in images as I, L, or T with rotation (0, 90, 180, 270).

Current prompt:
---
{current_prompt}
---

Below are misclassified cells. For each, I show:
- A generated REFERENCE image of what the correct answer looks like
- The actual cell image that was misclassified

Improve the prompt so the vision model classifies these correctly. Keep the prompt concise. Return only the improved prompt text."""},
    ]

    for f in failures:
        exp = f["expected"]
        got = f["got"]
        ref_img = refs[(exp["letter"], exp["rotation"])]

        content.append({"type": "text", "text": f"REFERENCE — this is {exp['letter']} at {exp['rotation']}°:"})
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{to_b64(ref_img)}"}})

        content.append({"type": "text", "text": (
            f"MISCLASSIFIED cell ({f['row']},{f['col']}): model said {got['letter']} at {got['rotation']}°, "
            f"but correct answer is {exp['letter']} at {exp['rotation']}°:"
        )})
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{to_b64(f['cell_image'])}"}})

    return llm([
        {"role": "user", "content": content}
    ], schema=PROMPT_IMPROVE_SCHEMA, max_tokens=2048)["prompt"]


def main():
    solution = load_solution()
    grid_data = load_png(GRID_IMAGE)
    cells = split_and_preprocess(grid_data)
    refs = generate_all_references()
    prompt = PROMPT_ASCII

    for i in range(MAX_ITERATIONS):
        print(f"\n=== Iteration {i + 1}/{MAX_ITERATIONS} ===")
        print(f"Prompt:\n{prompt}\n")

        results, failures = evaluate(cells, solution, prompt)

        correct = 9 - len(failures)
        print(f"Score: {correct}/9")

        if not failures:
            print("All cells classified correctly!")
            break

        print("Failures:")
        for f in failures:
            print(f"  ({f['row']},{f['col']}): expected {f['expected']}, got {f['got']}")

        prompt = improve_prompt(prompt, failures, refs)
        print(f"\nImproved prompt generated.")
    else:
        print(f"\nReached {MAX_ITERATIONS} iterations without perfect score.")

    # Save best prompt
    best_prompt_file = os.path.join(os.path.dirname(__file__), "best_prompt.txt")
    with open(best_prompt_file, "w") as f:
        f.write(prompt)
    print(f"Saved prompt to {best_prompt_file}")


if __name__ == "__main__":
    main()
