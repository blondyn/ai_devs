import json
import logging
import os

from common import api_get, get_api_key, llm_vision_call
from endpoints import DATA_ELECTRICITY, DATA_ELECTRICITY_SOLUTION
from s02e02.image_utils import (
    open_image, load_png, to_png_bytes, to_b64,
    save, split_grid_cells,
)
from s02e02.prompts import CELL_PROMPT, GRID_DETECT_PROMPT
from s02e02.schemas import SYMBOL_SCHEMA, GRID_SCHEMA, SYMBOL_TO_CELL

logger = logging.getLogger(__name__)

API_KEY = get_api_key()
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "images")


def vision_call(image_data, prompt, schema, model=None):
    """Send image + prompt to LLM with structured output."""
    kwargs = {"schema": schema}
    if model:
        kwargs["model"] = model
    return llm_vision_call([
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{to_b64(image_data)}"}},
            {"type": "text", "text": prompt},
        ]}
    ], **kwargs)


def detect_grid(image_data):
    """Ask LLM to find the 3x3 grid bounding box as relative coordinates."""
    bounds = vision_call(image_data, GRID_DETECT_PROMPT, GRID_SCHEMA)
    logger.info(f"Raw LLM bounds: {bounds}")

    # Normalize: if LLM returned 0-100 instead of 0.0-1.0, convert
    vals = [bounds["x_pct"], bounds["y_pct"], bounds["width_pct"], bounds["height_pct"]]
    if any(v > 1.0 for v in vals):
        bounds = {k: v / 100.0 for k, v in bounds.items()}

    w, h = open_image(image_data).size
    return {
        "x": int(bounds["x_pct"] * w),
        "y": int(bounds["y_pct"] * h),
        "width": int(bounds["width_pct"] * w),
        "height": int(bounds["height_pct"] * h),
    }


def extract_grid(image_data, name):
    """Detect grid in image, crop it, save, and return the cropped PNG bytes."""
    grid_bounds = detect_grid(image_data)
    logger.info(f"{name} grid bounds: {grid_bounds}")
    cropped = to_png_bytes(open_image(image_data).crop((
        grid_bounds["x"], grid_bounds["y"],
        grid_bounds["x"] + grid_bounds["width"],
        grid_bounds["y"] + grid_bounds["height"],
    )))
    save(cropped, f"{name}_grid.png", OUTPUT_DIR)
    return cropped


def analyze_image(image_data, model=None):
    """Split grid_only image into 3x3 cells, preprocess and classify each."""
    cells = split_grid_cells(image_data, should_preprocess=True)

    # Save preprocessed cells for debugging
    for r, row in enumerate(cells):
        for c, cell in enumerate(row):
            save(cell, f"debug_cell_{r}_{c}.png", OUTPUT_DIR)

    # Classify each cell
    results = []
    for r in range(3):
        row_results = []
        for c in range(3):
            result = vision_call(cells[r][c], CELL_PROMPT, SYMBOL_SCHEMA, model=model)
            symbol = result["symbol"]
            cell = SYMBOL_TO_CELL.get(symbol, {"letter": "?", "rotation": 0})
            logger.info(f"  Cell ({r},{c}): {symbol} -> {cell}")
            row_results.append(cell)
        results.append(row_results)
    return results


def compute_delta(problem, solution):
    """Compute rotation delta between problem and solution grids."""
    delta = []
    for r in range(3):
        row = []
        for c in range(3):
            p = problem[r][c]
            s = solution[r][c]
            if p["letter"] != s["letter"]:
                row.append({"letter": p["letter"], "error": f"letter mismatch: {p['letter']} vs {s['letter']}"})
            else:
                rot_diff = (s["rotation"] - p["rotation"]) % 360
                # I looks the same at 0/180 and 90/270, so minimize rotations
                if p["letter"] == "I" and rot_diff == 180:
                    rot_diff = 0
                elif p["letter"] == "I" and rot_diff == 270:
                    rot_diff = 90
                row.append({"letter": p["letter"], "current": p["rotation"], "target": s["rotation"], "delta": rot_diff})
        delta.append(row)
    return delta


def main():
    # Reset the puzzle state
    api_get(DATA_ELECTRICITY.format(api_key=API_KEY) + "?reset=1", "png")
    logger.info("Puzzle reset.")

    data = api_get(DATA_ELECTRICITY.format(api_key=API_KEY), "png")
    solution_data = api_get(DATA_ELECTRICITY_SOLUTION.format(api_key=API_KEY), "png")
    save(data, "electricity.png", OUTPUT_DIR)
    save(solution_data, "electricity_solution.png", OUTPUT_DIR)

    problem_grid = extract_grid(data, "problem")
    solution_grid = extract_grid(solution_data, "solution")

    logger.info("\n--- Analyzing problem grid ---")
    problem = analyze_image(problem_grid)

    logger.info("\n--- Analyzing solution grid ---")
    solution = analyze_image(solution_grid)

    logger.info("\n--- Rotation delta (how much to rotate each cell) ---")
    delta = compute_delta(problem, solution)

    logger.info("\n--- Sending solution ---")
    from s02e02.send_solution import send_solution
    responses = send_solution(delta, API_KEY)
    for r in responses:
        logger.info(r)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
