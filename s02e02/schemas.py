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
