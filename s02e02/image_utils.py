import base64
import io
import logging
import os

from PIL import Image

logger = logging.getLogger(__name__)


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


def save(data, name, output_dir):
    path = os.path.join(output_dir, name)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
        logger.info(f"Saved {len(data)} bytes to {path}")


def split_grid_cells(image_data, rows=3, cols=3, should_preprocess=True):
    """Split image into grid cells, return 2D list of preprocessed PNG bytes."""
    img = open_image(image_data)
    w, h = img.size
    cell_w, cell_h = w // cols, h // rows
    cells = []
    for r in range(rows):
        row = []
        for c in range(cols):
            box = (c * cell_w, r * cell_h, (c + 1) * cell_w, (r + 1) * cell_h)
            cell = preprocess(to_png_bytes(img.crop(box))) if should_preprocess else to_png_bytes(img.crop(box))
            row.append(cell)
        cells.append(row)
    return cells
