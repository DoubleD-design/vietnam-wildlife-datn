from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from app.models.schemas import SpeciesCandidateResponse


@dataclass
class ChatSessionState:
    current_species_id: str | None = None
    current_species_name: str | None = None
    pending_question: str | None = None
    awaiting_confirmation: bool = False
    pending_candidates: list[SpeciesCandidateResponse] = field(default_factory=list)
    recent_multi_species_entities: list[dict] = field(default_factory=list)


class InMemoryChatSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ChatSessionState] = {}
        self._guard = threading.Lock()

    def get(self, session_id: str) -> ChatSessionState:
        with self._guard:
            return self._sessions.setdefault(session_id, ChatSessionState())

    def save(self, session_id: str, state: ChatSessionState) -> None:
        with self._guard:
            self._sessions[session_id] = state


class SessionLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    @contextmanager
    def lock(self, session_id: str) -> Iterator[None]:
        with self._guard:
            lock = self._locks.setdefault(session_id, threading.Lock())

        lock.acquire()
        try:
            yield
        finally:
            lock.release()
