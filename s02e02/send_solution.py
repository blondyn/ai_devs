import logging

from common import submit

logger = logging.getLogger(__name__)


def send_solution(delta, api_key):
    """Send rotation commands based on computed delta."""
    responses = []
    for r, row in enumerate(delta):
        for c, cell in enumerate(row):
            if cell.get("delta", 0) != 0:
                rotations = cell["delta"] // 90
                position = f"{r+1}x{c+1}"
                for i in range(abs(rotations)):
                    logger.info(f"Rotating {position} ({i+1}/{rotations})")
                    response = submit(api_key=api_key, task="electricity", answer={"rotate": position})
                    responses.append(response)
    return responses
