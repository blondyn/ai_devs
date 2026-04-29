from pathlib import Path


def read_file(path: str) -> str:
    return Path(path).read_text()


def write_file(path: str, content: str) -> str:
    Path(path).write_text(content)
    return f"Written {len(content)} chars to {path}"


def delegate(agent_type: str, task: str) -> str:
    from agent import run_agent
    return run_agent(agent_type, task)


HANDLERS = {
    "read_file": read_file,
    "write_file": write_file,
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
