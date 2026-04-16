CELL_PROMPT = """Look at this pipe segment image. The top of the image is UP.

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

GRID_DETECT_PROMPT = """Look at this image. There is a 3x3 grid of cells containing pipe/maze segments drawn with thin black lines.

Find the bounding box of just the 3x3 inner grid area (excluding any labels, icons, or text outside the grid).

Return the coordinates as fractions of the image dimensions (0.0 to 1.0):
- x_pct: left edge as fraction of image width
- y_pct: top edge as fraction of image height
- width_pct: grid width as fraction of image width
- height_pct: grid height as fraction of image height"""
