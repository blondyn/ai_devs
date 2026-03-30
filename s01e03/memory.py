from abc import ABC, abstractmethod


class ConversationMemory(ABC):
    @abstractmethod
    def add(self, session_id: str, role: str, msg: str):
        pass

    @abstractmethod
    def get(self, session_id: str) -> list[dict]:
        pass


class InMemoryConversationMemory(ConversationMemory):
    def __init__(self):
        self._store: dict[str, list[dict]] = {}

    def add(self, session_id: str, role: str, msg: str):
        if session_id not in self._store:
            self._store[session_id] = []
        self._store[session_id].append({"role": role, "msg": msg})

    def get(self, session_id: str) -> list[dict]:
        return self._store.get(session_id, [])
