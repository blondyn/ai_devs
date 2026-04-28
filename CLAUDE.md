# Project conventions

## Code style
- Prefer short, single-purpose functions. If a function needs a comment to explain what it does, it should probably be split.

## OpenRouter / LLM calls
- Minimise tokens sent to OpenRouter: keep system prompts tight, avoid sending raw log dumps in messages, and use cache/slice patterns to pass only relevant data to the model.
- When building tool results that feed back into the LLM context, return only what the model needs — counts, summaries, and structured fields rather than full raw text.
