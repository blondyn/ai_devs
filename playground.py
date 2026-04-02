"""
Interactive playground — chat with an LLM that has web search via OpenRouter's :online plugin.

Usage:
    python3 playground.py [model]

Example:
    python3 playground.py
    python3 playground.py anthropic/claude-sonnet-4-6
"""
import os
import sys

from common import load_dotenv, llm, cost_tracker

load_dotenv()
MODEL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LLM_MODEL", "gpt-4o-mini")
ONLINE_MODEL = f"{MODEL}:online"

SYSTEM = (
    "You are a helpful assistant with web search enabled. "
    "You can answer questions about recent events, look up people, and provide current information. "
    "Always cite your sources with URLs when using web results."
)

if __name__ == "__main__":
    print(f"Playground (model: {ONLINE_MODEL})")
    print("Chat freely — web search is built in.")
    print("Commands: 'new' to clear context, 'quit' to exit\n")

    history = [{"role": "system", "content": SYSTEM}]

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break
        if user_input.lower() == "new":
            history = [{"role": "system", "content": SYSTEM}]
            print("[Context cleared.]\n")
            continue

        history.append({"role": "user", "content": user_input})

        answer = llm(history, max_tokens=2048, model=ONLINE_MODEL)
        history.append({"role": "assistant", "content": answer})
        print(f"\nAssistant: {answer}\n")
        print(f"  [{cost_tracker.summary()}]\n")
