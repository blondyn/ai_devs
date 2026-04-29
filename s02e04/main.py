from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml

from common import agent_loop
# from tools import build_tools, HANDLERS
from s02e04.agent import run_agent


def main():
    agent = run_agent("orchestrator", "")
    task = input("Task: ")
    messages = [{"role": "user", "content": task}]
    # result = agent_loop(
    #     messages=messages,
    #     tools=build_tools(agent.tools),
    #     tool_handlers=HANDLERS,
    #     system=agent.prompt,
    #     model=agent.model,
    # )
    print('')


if __name__ == "__main__":
    main()
