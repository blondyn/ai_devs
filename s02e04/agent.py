from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import frontmatter

from common import agent_loop
from s02e04.tools import HANDLERS, build_tools

AGENTS_DIR = Path(__file__).parent / "agents"
MAX_TURNS = 10


@dataclass
class AgentDef:
    name: str
    prompt: str
    model: Optional[str] = None
    tools: list[str] = field(default_factory=list)


def load_agent(agent_type: str) -> AgentDef:
    post = frontmatter.load(AGENTS_DIR / f"{agent_type}.md")
    return AgentDef(
        name=post.get("name", agent_type),
        model=post.get("model"),
        tools=post.get("tools", []),
        prompt=post.content.strip(),
    )


def run_agent(agent_name: str, task: str) -> str:
    print(f"Starting: {agent_name}")
    agent = load_agent(agent_name)
    messages = [
        {"role": "system", "content": agent.prompt},
        {"role": "user", "content": task},
    ]
    tool_schemas = [HANDLERS[tool_name] for tool_name in agent.tools if HANDLERS[tool_name]]
    tool_handlers = {name: HANDLERS[name] for name in agent.tools if name in HANDLERS}


    # result, _ = agent_loop(
    #     messages=messages,
    #     tools=tool_schemas,
    #     tool_handlers=tool_handlers,
    #     model=agent.model,
    #     max_iterations=MAX_TURNS,
    # )
    return result
