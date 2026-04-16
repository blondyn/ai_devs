import base64
import io
import os
import json

from PIL import Image

from common import api_get, get_api_key, llm_vision_call
from endpoints import DATA_ELECTRICITY, DATA_ELECTRICITY_SOLUTION

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


def preprocess(data, threshold=128, margin=15):
    """Convert image to clean black & white, crop margins to remove grid lines."""
    img = open_image(data)
    w, h = img.size
    img = img.crop((margin, margin, w - margin, h - margin))
    img = img.convert("L")
    img = img.point(lambda x: 255 if x > threshold else 0, "1")
    return to_png_bytes(img)
PROMPT = """Classify this pipe segment as I, L, or T with its rotation (0, 90, 180, or 270 degrees clockwise).

I: straight line. 0° = vertical, 90° = horizontal.

L: corner/elbow. 0° = arms go right and up (standard L). 90° = arms go right and down. 180° = arms go left and down. 270° = arms go left and up.

T: T-junction. 0° = top bar horizontal, stem goes down. 90° = bar vertical, stem goes left. 180° = bottom bar horizontal, stem goes up. 270° = bar vertical, stem goes right.
"""

PROMPT_ASCII = """Classify this pipe segment as I, L, or T with its rotation.

I (straight):
  0°:  |     90°: ───
       |

L (corner):
  0°:  └──     90°: ┌──     180°: ──┐      270°: ──┘

T (T-junction):
  0°:  ───    90°:  |     180°:  |     270°: |
        |         ──┤           ├──         ├──
                    |            |           |
"""

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "grid_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "letter": {"type": "string"},
                                "rotation": {"type": "integer"},
                            },
                            "required": ["letter", "rotation"],
                            "additionalProperties": False,
                        },
                    },
                },
            },
            "required": ["rows"],
            "additionalProperties": False,
        },
    },
}


def save(data, name):
    path = os.path.join(OUTPUT_DIR, name)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
        print(f"Saved {len(data)} bytes to {path}")




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


CELL_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "cell_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "letter": {"type": "string"},
                "rotation": {"type": "integer"},
            },
            "required": ["letter", "rotation"],
            "additionalProperties": False,
        },
    },
}


def vision_call(image_data, prompt, schema):
    """Send image + prompt to LLM with structured output."""
    return llm_vision_call([
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{to_b64(image_data)}"}},
            {"type": "text", "text": prompt},
        ]}
    ], schema=schema)


def detect_grid(image_data):
    """Ask LLM to find the 3x3 grid bounding box as relative coordinates."""
    bounds = vision_call(image_data, GRID_DETECT_PROMPT, GRID_SCHEMA)
    w, h = open_image(image_data).size
    return {
        "x": int(bounds["x_pct"] * w),
        "y": int(bounds["y_pct"] * h),
        "width": int(bounds["width_pct"] * w),
        "height": int(bounds["height_pct"] * h),
    }


def split_grid(image_data, grid_bounds):
    """Split image into 3x3 cells using detected grid bounds."""
    img = open_image(image_data)
    gx, gy, gw, gh = grid_bounds["x"], grid_bounds["y"], grid_bounds["width"], grid_bounds["height"]
    cell_w, cell_h = gw // 3, gh // 3
    cells = []
    for r in range(3):
        row = []
        for c in range(3):
            box = (gx + c * cell_w, gy + r * cell_h, gx + (c + 1) * cell_w, gy + (r + 1) * cell_h)
            row.append(preprocess(to_png_bytes(img.crop(box))))
        cells.append(row)
    return cells


def analyze_image(image_data):
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
            result = vision_call(cells[r][c], PROMPT_ASCII, CELL_SCHEMA)
            print(f"  Cell ({r},{c}): {result}")
            row_results.append(result)
        results.append(row_results)
    return {"rows": results}


def main():
    data = api_get(DATA_ELECTRICITY.format(api_key=API_KEY), "png")
    solution = api_get(DATA_ELECTRICITY_SOLUTION.format(api_key=API_KEY), "png")
    save(data, "electricity.png")
    save(solution, "electricity_solution.png")

    grid_bounds = detect_grid(data)
    print(f"Detected grid bounds: {grid_bounds}")

    save(to_png_bytes(open_image(data).crop((
        grid_bounds["x"], grid_bounds["y"],
        grid_bounds["x"] + grid_bounds["width"],
        grid_bounds["y"] + grid_bounds["height"],
    ))), "grid_only.png")

    analyze_image(load_png(os.path.join(OUTPUT_DIR,"grid_only.png")))


if __name__ == "__main__":
    main()
