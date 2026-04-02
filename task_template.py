"""
s01eXX — Brief description of the task.
"""
import json
import os

from common import load_dotenv, get_api_key, llm, submit, agent_loop, save_result, cost_tracker

load_dotenv()
api_key = get_api_key()
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
TASK_DIR = os.path.dirname(__file__)


def solve():
    """Main task logic."""
    # 1. Fetch data
    # data = api_get(endpoint) or download from URL

    # 2. Process with LLM
    # Option A: Single LLM call
    # answer = llm(messages, schema=SCHEMA, model=LLM_MODEL)

    # Option B: Agent loop with tools
    # answer, messages = agent_loop(
    #     messages=[{"role": "system", "content": "..."}],
    #     tools=TOOLS,
    #     tool_handlers={"tool_name": handler_fn},
    #     model=LLM_MODEL,
    # )

    # 3. Submit
    # result = submit(api_key, "task_name", answer)

    # 4. Save results (optional)
    # save_result(TASK_DIR, {"answer": answer, "response": result})
    pass


if __name__ == "__main__":
    solve()
    print(f"\n{cost_tracker.summary()}")
