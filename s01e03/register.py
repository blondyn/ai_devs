import os
import sys
import uuid
from datetime import datetime

from common import get_api_key, submit

api_key = get_api_key()
public_url = os.environ.get("PUBLIC_URL")
if not public_url:
    print("PUBLIC_URL not set")
    sys.exit(1)

session_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]

submit(api_key, "proxy", {
    "url": public_url,
    "sessionID": session_id,
})
