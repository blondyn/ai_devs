import json
import logging

import tiktoken

from common import interactive_agent_loop, get_api_key

logger = logging.getLogger(__name__)

API_KEY = get_api_key()

SYSTEM_PROMPT = "You are a helpful assistant."


def count_tokens(text, model="gpt-4o"):
    """Count tokens in text using tiktoken."""
    enc = tiktoken.encoding_for_model(model)
    count = len(enc.encode(text))
    return json.dumps({"token_count": count, "model": model, "text_length": len(text)})


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "count_tokens",
            "description": "Count the number of tokens in a given text using tiktoken. Useful for estimating API costs or checking context window limits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to count tokens for"},
                    "model": {"type": "string", "description": "Model to use for tokenization (default: gpt-4o)", "default": "gpt-4o"},
                },
                "required": ["text"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "count_tokens": count_tokens,
}



GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def on_tool_call(name, args, result):
    logger.info(f"{YELLOW}Tool: {name}({json.dumps(args)}) -> {result}{RESET}")


def chat():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input(f"\n{GREEN}You: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            break

        messages.append({"role": "user", "content": user_input})

        answer, messages = interactive_agent_loop(
            messages,
            tools=TOOLS or None,
            tool_handlers=TOOL_HANDLERS,
            on_tool_call=on_tool_call,
        )

        if answer:
            print(f"\n{CYAN}Assistant:{RESET} {answer}")
        else:
            print("\n[No response - max iterations reached]")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    chat()
