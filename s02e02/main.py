import base64
import os
from datetime import datetime

from common import api_get, get_api_key, llm_vision_call
from endpoints import DATA_ELECTRICITY, DATA_ELECTRICITY_SOLUTION

API_KEY = get_api_key()
OUTPUT_DIR = os.path.dirname(__file__)
PROMPT = """
You are a classifier system that can classify maze on the image. The image is a 2D grid with 3 rows and 3 columns.

You have to categorize the image cells into 3 different types:
- letter I - a straight vertical line
- letter L - a corner with 90deg
- letter T - three way junction

The letters can be rotated around the clock in 90 degrees with the anchor in the center of the cell.

Analyze the provided image and give me a response for each row with their respective letter rotation for each cell.

The response should be returned in the following format with array(cells) within array (rows)

[
    [{T, 90}, {I,0},{T, 270}], // row1
    [{T, 90}, {I,0},{T, 270}] // row2
    [{T, 90}, {I,0},{T, 270}] // row3
]

"""

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "grid_classification",
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
                                "type": {"type": "string", "enum": ["I", "L", "T"]},
                                "rotation": {"type": "integer", "enum": [0, 90, 180, 270]},
                            },
                            "required": ["type", "rotation"],
                        },
                    },
                },
            },
            "required": ["rows"],
        },
    },
}


def save(data, name, include_timestamp=False):
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    if include_timestamp:
        filename = f"{timestamp}_{name}"
    else:
        filename = f"{name}"


    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
        print(f"Saved {len(data)} bytes to {path}")




def analyze_image(image_data):
    img_b64 = base64.b64encode(image_data).decode()
    return llm_vision_call([
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            {"type": "text", "text": PROMPT},
        ]}
    ], schema=SCHEMA)


def main():
    data = api_get(DATA_ELECTRICITY.format(api_key=API_KEY), "png")
    solution = api_get(DATA_ELECTRICITY_SOLUTION.format(api_key=API_KEY), "png")
    save(data, "electricity.png", include_timestamp=True)
    save(solution, "electricity_solution.png")

    result = analyze_image(data)
    print(result)


if __name__ == "__main__":
    main()
