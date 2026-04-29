from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import frontmatter
import requests
import os
import sys

from common import agent_loop
from s02e04.tools import HANDLERS, build_tools

AGENTS_DIR = Path(__file__).parent / "agents"
MAX_TURNS = 2


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

def call_llm(messages, schema=None, tools=None, temperature=None):
    openrouter_key = os.environ.get('OPENROUTER_API_KEY')
    if not openrouter_key:
        print('OR key not set')
        sys.exit(1)
    default_model = os.environ.get("LLM_MODEL", "google/gemini-2.0-flash-001")
    body = {
        "model": default_model,
        "messages": messages

    }

    if schema:
        body["response_format"] = schema
    if tools:
        body["tools"] = tools
    if temperature is not None:
        body["temperature"] = temperature

    headers = {
        "Authorization": f"Bearer {openrouter_key}"
    }
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=body
    )
    
    print(resp.status_code)

    return resp;


def find_tool(name: str):
    HANDLERS[str]()

def run_agent(agent_name: str, task: str) -> str:
    print(f"Starting: {agent_name}")
    agent = load_agent(agent_name)

    messages = [
        {"role": "system", "content": agent.prompt},
        {"role": "user", "content": task},
    ]

    # run until max turns to figure out the problem
    for n in range(MAX_TURNS):
        resp = call_llm(messages)
        choices = resp.json()['choices']
        
        for i, choice in enumerate(choices):
            message = choice['message']
            if not message:
                return "Agent error; no response from the model"

            print(f"{agent_name}: {i+1}: {message}")
            msg = {
                "role": "assistant",
                "content": message['content'],
            }

            if "tool_calls" not in message:
                print(f"{agent_name} completed")
                return message.content
            
            msg["tool_calls"] = message["tool_calls"]
            messages.append(msg)

            for tool_call in message["tool_calls"]:
                if tool_call["type"] is not 'function':
                    continue
                
                fn = tool_call["function"]
                fn_name, fn_args = fn["name"], fn["arguments"]
                print(f"{agent_name}: Tool {fn_name} called")

                tool = find_tool(fn_name)                   
                    




            return message['content']
        n =+ 1
    
    tool_schemas = [HANDLERS[tool_name] for tool_name in agent.tools if HANDLERS[tool_name]]
    tool_handlers = {name: HANDLERS[name] for name in agent.tools if name in HANDLERS}


    # result, _ = agent_loop(
    #     messages=messages,
    #     tools=tool_schemas,
    #     tool_handlers=tool_handlers,
    #     model=agent.model,
    #     max_iterations=MAX_TURNS,
    # )
    # return result
