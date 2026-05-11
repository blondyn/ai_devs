from pathlib import Path

from common import submit, get_api_key, api_post


def read_file(path: str) -> str:
    return Path(path).read_text()


def write_file(path: str, content: str) -> str:
    Path(path).write_text(content)
    return f"Written {len(content)} chars to {path}"


def fetch_mail(payload: dict) -> str:
    result = api_post("/api/zmail", payload)
    return str(result)


def verify(task: str, answer: str) -> str:
    result = submit(get_api_key(), task, answer)
    return str(result)


def delegate(agent_type: str, task: str) -> str:
    from s02e04.agent import run_agent
    return run_agent(agent_type, task)


HANDLERS = {
    "read_file": read_file,
    "write_file": write_file,
    "fetch_mail": fetch_mail,
    "verify": verify,
    "delegate": delegate,
}

SCHEMAS = {
    "read_file": {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                },
                "required": ["path"],
            },
        },
    },
    "write_file": {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    "fetch_mail": {
        "type": "function",
        "function": {
            "name": "fetch_mail",
            "description": "POST to /api/zmail and return the response.",
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {"type": "object", "description": "JSON payload to send"},
                },
                "required": ["payload"],
            },
        },
    },
    "verify": {
        "type": "function",
        "function": {
            "name": "verify",
            "description": "Submit an answer to the /verify endpoint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task identifier"},
                    "answer": {"type": "string", "description": "Answer to submit"},
                },
                "required": ["task", "answer"],
            },
        },
    },
    "delegate": {
        "type": "function",
        "function": {
            "name": "delegate",
            "description": "Delegate a subtask to a specialist agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_type": {"type": "string", "description": "Agent definition name (filename without .md)"},
                    "task": {"type": "string", "description": "Task description for the agent"},
                },
                "required": ["agent_type", "task"],
            },
        },
    },
}


def build_tools(names: list[str]) -> list[dict]:
    return [SCHEMAS[n] for n in names if n in SCHEMAS]
