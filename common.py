import json
import os
import sys
import urllib.request

BASE_URL = os.environ.get("API_BASE_URL", "https://hub.ag3nts.org")

def load_dotenv():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip()

def get_api_key():
    load_dotenv()
    key = os.environ.get('AGENTS_KEY')
    if not key:
        print("AGENTS_KEY not set")
        sys.exit(1)
    return key

class ApiError(Exception):
    def __init__(self, code, body):
        self.code = code
        self.body = body
        super().__init__(f"HTTP {code}: {body}")

def api_post(endpoint, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}{endpoint}", data=data,
                                headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode('utf-8'))
    return json.loads(resp.read().decode('utf-8'))

def api_get(path):
    with urllib.request.urlopen(f"{BASE_URL}{path}") as resp:
        return json.loads(resp.read().decode('utf-8'))

def llm_call(messages, schema, max_tokens=1024, model="google/gemini-2.0-flash-001"):
    openrouter_key = os.environ.get('OPENROUTER_API_KEY')
    if not openrouter_key:
        print("OPENROUTER_API_KEY not set")
        sys.exit(1)
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "response_format": schema
    }).encode('utf-8')
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {openrouter_key}"}
    )
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
        sys.exit(1)
    result = json.loads(resp.read().decode('utf-8'))
    return json.loads(result['choices'][0]['message']['content'])

def llm_vision_call(messages, schema=None, max_tokens=1024, model="google/gemini-2.0-flash-001"):
    openrouter_key = os.environ.get('OPENROUTER_API_KEY')
    if not openrouter_key:
        print("OPENROUTER_API_KEY not set")
        sys.exit(1)
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if schema:
        body["response_format"] = schema
    payload = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {openrouter_key}"}
    )
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
        sys.exit(1)
    result = json.loads(resp.read().decode('utf-8'))
    content = result['choices'][0]['message']['content']
    if schema:
        return json.loads(content)
    return content

def submit(api_key, task, answer):
    from endpoints import VERIFY
    result = api_post(VERIFY, {"apikey": api_key, "task": task, "answer": answer})
    print(f"Response: {json.dumps(result, indent=2)}")
    return result
