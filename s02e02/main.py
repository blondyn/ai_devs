import base64
import io
import os
import json
import logging

from PIL import Image

from common import api_get, get_api_key, llm_vision_call
from endpoints import DATA_ELECTRICITY, DATA_ELECTRICITY_SOLUTION

logger = logging.getLogger(__name__)
# logger.setLevel(logging.WARNING)

API_KEY = get_api_key()
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "images")


def open_image(data):
    return Image.open(io.BytesIO(data))


def load_png(path):
    with open(path, "rb") as f:
        return f.read()


def to_png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def to_b64(data):
    return base64.b64encode(data).decode()


def preprocess(data, threshold=128, margin=15, padding=10):
    """Convert image to clean black & white, crop margins and add white padding."""
    img = open_image(data)
    w, h = img.size
    img = img.crop((margin, margin, w - margin, h - margin))
    img = img.convert("L")
    img = img.point(lambda x: 255 if x > threshold else 0, "1")
    padded = Image.new("1", (img.width + 2 * padding, img.height + 2 * padding), 1)
    padded.paste(img, (padding, padding))
    return to_png_bytes(padded)


PROMPT = """Look at this pipe segment image. The top of the image is UP.

Step 1: Does a line extend UP from center? (yes/no)
Step 2: Does a line extend DOWN from center? (yes/no)
Step 3: Does a line extend LEFT from center? (yes/no)
Step 4: Does a line extend RIGHT from center? (yes/no)

Step 5: Based on your answers, match to one of these symbols:
│ = up+down    ── = left+right
┗ = up+right   ┏ = down+right   ┓ = down+left   ┛ = up+left
┳ = left+right+down   ┫ = up+down+left   ┻ = left+right+up   ┣ = up+down+right

Return the matching symbol.
"""

SYMBOL_TO_CELL = {
    "│":  {"letter": "I", "rotation": 0},
    "──": {"letter": "I", "rotation": 90},
    "┗":  {"letter": "L", "rotation": 0},
    "┏":  {"letter": "L", "rotation": 90},
    "┓":  {"letter": "L", "rotation": 180},
    "┛":  {"letter": "L", "rotation": 270},
    "┳":  {"letter": "T", "rotation": 0},
    "┫":  {"letter": "T", "rotation": 90},
    "┻":  {"letter": "T", "rotation": 180},
    "┣":  {"letter": "T", "rotation": 270},
}

SYMBOL_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "symbol_match",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "up": {"type": "boolean"},
                "down": {"type": "boolean"},
                "left": {"type": "boolean"},
                "right": {"type": "boolean"},
                "symbol": {"type": "string"},
            },
            "required": ["up", "down", "left", "right", "symbol"],
            "additionalProperties": False,
        },
    },
}


def save(data, name):
    path = os.path.join(OUTPUT_DIR, name)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
        logger.info(f"Saved {len(data)} bytes to {path}")


GRID_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "grid_bounds",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "x_pct": {"type": "number", "description": "Left edge as fraction 0.0-1.0"},
                "y_pct": {"type": "number", "description": "Top edge as fraction 0.0-1.0"},
                "width_pct": {"type": "number", "description": "Width as fraction 0.0-1.0"},
                "height_pct": {"type": "number", "description": "Height as fraction 0.0-1.0"},
            },
            "required": ["x_pct", "y_pct", "width_pct", "height_pct"],
            "additionalProperties": False,
        },
    },
}

GRID_DETECT_PROMPT = """Look at this image. There is a 3x3 grid of cells containing pipe/maze segments drawn with thin black lines.

Find the bounding box of just the 3x3 inner grid area (excluding any labels, icons, or text outside the grid).

Return the coordinates as fractions of the image dimensions (0.0 to 1.0):
- x_pct: left edge as fraction of image width
- y_pct: top edge as fraction of image height
- width_pct: grid width as fraction of image width
- height_pct: grid height as fraction of image height"""


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


def analyze_image(image_data, model=None):
    """Split grid_only image into 3x3 cells, preprocess and classify each."""
    img = open_image(image_data)
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

    # Save preprocessed cells for debugging
    for r, row in enumerate(cells):
        for c, cell in enumerate(row):
            save(cell, f"debug_cell_{r}_{c}.png")

    # Classify each cell
    results = []
    for r in range(3):
        row_results = []
        for c in range(3):
            result = vision_call(cells[r][c], PROMPT, SYMBOL_SCHEMA, model=model)
            symbol = result["symbol"]
            cell = SYMBOL_TO_CELL.get(symbol, {"letter": "?", "rotation": 0})
            logger.info(f"  Cell ({r},{c}): {symbol} -> {cell}")
            row_results.append(cell)
        results.append(row_results)
    return results


def extract_grid(image_data, name):
    """Detect grid in image, crop it, save, and return the cropped PNG bytes."""
    grid_bounds = detect_grid(image_data)
    logger.info(f"{name} grid bounds: {grid_bounds}")
    cropped = to_png_bytes(open_image(image_data).crop((
        grid_bounds["x"], grid_bounds["y"],
        grid_bounds["x"] + grid_bounds["width"],
        grid_bounds["y"] + grid_bounds["height"],
    )))
    save(cropped, f"{name}_grid.png")
    return cropped


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
    save(data, "electricity.png")
    save(solution_data, "electricity_solution.png")

    problem_grid = extract_grid(data, "problem")
    solution_grid = extract_grid(solution_data, "solution")

    logger.info("\n--- Analyzing problem grid ---")
    problem = analyze_image(problem_grid, model="anthropic/claude-opus-4.7")
    # logger.info(json.dumps(problem, indent=2))

    logger.info("\n--- Analyzing solution grid ---")
    solution = analyze_image(solution_grid, model="anthropic/claude-opus-4.7")
    # logger.info(json.dumps(solution, indent=2))

    logger.info("\n--- Rotation delta (how much to rotate each cell) ---")
    delta = compute_delta(problem, solution)
    # logger.info(json.dumps(delta, indent=2))

    logger.info("\n--- Sending solution ---")
    from s02e02.send_solution import send_solution
    responses = send_solution(delta, API_KEY)
    for r in responses:
        logger.info(r)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
