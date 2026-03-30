import json
from abc import ABC, abstractmethod


class ConversationMemory(ABC):
    @abstractmethod
    def add(self, session_id: str, role: str, msg: str):
        pass

    @abstractmethod
    def get(self, session_id: str) -> list[dict]:
        pass

    @abstractmethod
    def dump(self):
        pass


class InMemoryConversationMemory(ConversationMemory):
    def __init__(self, dump_path: str = "conversations.json"):
        self._store: dict[str, list[dict]] = {}
        self._dump_path = dump_path

    def add(self, session_id: str, role: str, msg: str):
        if session_id not in self._store:
            self._store[session_id] = []
        self._store[session_id].append({"role": role, "msg": msg})

    def get(self, session_id: str) -> list[dict]:
        return self._store.get(session_id, [])

    def dump(self):
        with open(self._dump_path, "w") as f:
            json.dump(self._store, f, indent=2, ensure_ascii=False)
        print(f"Conversations saved to {self._dump_path}")
