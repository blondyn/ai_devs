"""
Explorer agent — downloads a markdown document, follows [include file="..."] directives,
and returns all content (text + images) as a structured knowledge base.

Supports interactive chat (REPL) and programmatic ask() for other agents.
"""
import base64
import re
import urllib.request

from common import BASE_URL, llm_call, llm_vision_call
from endpoints import DATA_DOC

DOC_BASE = f"{BASE_URL}{DATA_DOC}"


def _download_text(url):
    print(f"  [Explorer] Downloading {url}")
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode("utf-8")


def _download_binary(url):
    print(f"  [Explorer] Downloading {url}")
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def _parse_includes(markdown):
    return re.findall(r'\[include file="([^"]+)"\]', markdown)


def _resolve_includes(index_md, base_url):
    """Download all included files referenced in the index document."""
    includes = _parse_includes(index_md)
    print(f"  [Explorer] Found {len(includes)} includes: {includes}")

    files = {}
    for fname in includes:
        url = f"{base_url}{fname}"
        if fname.lower().endswith((".png", ".jpg", ".jpeg")):
            raw = _download_binary(url)
            ext = fname.rsplit(".", 1)[-1].lower()
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}[ext]
            files[fname] = {
                "type": "image",
                "mime": mime,
                "base64": base64.b64encode(raw).decode("utf-8"),
            }
        else:
            files[fname] = {
                "type": "text",
                "content": _download_text(url),
            }
    return files


def explore(base_url=DOC_BASE):
    """
    Download the index document and all its includes.

    Returns a dict:
        {
            "index": <str>,           # raw markdown of index.md
            "files": {
                "filename.md": {"type": "text", "content": "..."},
                "image.png":   {"type": "image", "mime": "image/png", "base64": "..."},
                ...
            }
        }
    """
    print("[Explorer] Fetching index.md...")
    index_md = _download_text(f"{base_url}index.md")

    print("[Explorer] Resolving includes...")
    files = _resolve_includes(index_md, base_url)

    print(f"[Explorer] Done. {len(files)} files collected.")
    return {"index": index_md, "files": files}


class Explorer:
    """Stateful explorer that downloads documents once and answers questions about them."""

    def __init__(self, base_url=DOC_BASE):
        self._base_url = base_url
        self._knowledge = None
        self._context = None
        self._history = []

    def load(self):
        """Download all documents. Call once before asking questions."""
        self._knowledge = explore(self._base_url)
        self._context = self._build_context()
        self._history = [
            {"role": "system", "content": (
                "Jesteś ekspertem systemu SPK (System Przesyłek Konduktorskich). "
                "Masz dostęp do pełnej dokumentacji technicznej SPK. "
                "Odpowiadaj na pytania na podstawie dokumentacji. "
                "Jeśli pytanie dotyczy obrazu (mapy tras), masz jego opis w kontekście.\n\n"
                f"DOKUMENTACJA:\n{self._context}"
            )}
        ]
        return self

    def _build_context(self):
        parts = [f"=== index.md ===\n{self._knowledge['index']}"]
        for fname, fdata in self._knowledge["files"].items():
            if fdata["type"] == "text":
                parts.append(f"=== {fname} ===\n{fdata['content']}")
            elif fdata["type"] == "image":
                desc = self._describe_image(fname, fdata)
                parts.append(f"=== {fname} (obraz) ===\n{desc}")
        return "\n\n".join(parts)

    def _describe_image(self, fname, fdata):
        print(f"  [Explorer] Analyzing image: {fname}")
        return llm_vision_call(
            messages=[
                {"role": "system", "content": "Opisz dokładnie co widzisz na obrazku. Wymień wszystkie lokalizacje, trasy, oznaczenia."},
                {"role": "user", "content": [
                    {"type": "text", "text": f"Opisz ten obraz ({fname}):"},
                    {"type": "image_url", "image_url": {"url": f"data:{fdata['mime']};base64,{fdata['base64']}"}}
                ]}
            ]
        )

    def ask(self, question, schema=None, max_tokens=1024):
        """Ask a question about the loaded documents. Used by other agents programmatically."""
        if not self._knowledge:
            raise RuntimeError("Call load() first")

        self._history.append({"role": "user", "content": question})

        if schema:
            answer = llm_call(self._history, schema=schema, max_tokens=max_tokens)
            self._history.append({"role": "assistant", "content": str(answer)})
            return answer
        else:
            answer = llm_vision_call(self._history, max_tokens=max_tokens)
            self._history.append({"role": "assistant", "content": answer})
            return answer

    def chat(self):
        """Interactive REPL for chatting with the explorer."""
        if not self._knowledge:
            self.load()

        print("\n[Explorer] Chat mode. Type 'quit' to exit.\n")
        while True:
            try:
                question = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[Explorer] Bye.")
                break
            if not question or question.lower() in ("quit", "exit", "q"):
                print("[Explorer] Bye.")
                break

            answer = self.ask(question)
            print(f"\nExplorer: {answer}\n")


if __name__ == "__main__":
    from common import load_dotenv, get_api_key
    load_dotenv()
    get_api_key()
    Explorer().chat()
