from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from app.models.schemas import SpeciesCandidateResponse


@dataclass
class ConversationTurn:
    question: str
    resolved_question: str
    intents: list[str] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    answer: str = ""
    evidence: list[dict] = field(default_factory=list)


@dataclass
class ChatSessionState:
    current_species_id: str | None = None
    current_species_name: str | None = None
    pending_question: str | None = None
    awaiting_confirmation: bool = False
    pending_candidates: list[SpeciesCandidateResponse] = field(default_factory=list)
    recent_multi_species_entities: list[dict] = field(default_factory=list)
    focus_mode: str = "none"
    focused_entities: list[dict] = field(default_factory=list)
    last_intents: list[str] = field(default_factory=list)
    last_question: str | None = None
    last_answer: str | None = None
    last_evidence: list[dict] = field(default_factory=list)
    recent_turns: list[ConversationTurn] = field(default_factory=list)
    last_activity_at: float = field(default_factory=time.time)
    pending_action: str | None = None
    pending_entities: list[dict] = field(default_factory=list)
    pending_entity_index: int | None = None
    pending_clarification_question: str | None = None
    pending_clarification_entities: list[dict] = field(default_factory=list)

    def touch(self) -> None:
        self.last_activity_at = time.time()

    def add_turn(self, turn: ConversationTurn, limit: int = 6) -> None:
        self.recent_turns.append(turn)
        self.recent_turns = self.recent_turns[-limit:]
        self.last_question = turn.resolved_question
        self.last_answer = turn.answer
        self.last_intents = list(turn.intents)
        self.last_evidence = list(turn.evidence)
        self.touch()


class InMemoryChatSessionStore:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._sessions: dict[str, ChatSessionState] = {}
        self._guard = threading.Lock()
        self._ttl_seconds = ttl_seconds

    def get(self, session_id: str) -> ChatSessionState:
        with self._guard:
            now = time.time()
            self._purge_expired(now)
            state = self._sessions.get(session_id)
            if state is None:
                state = ChatSessionState()
                self._sessions[session_id] = state
            state.last_activity_at = now
            return state

    def save(self, session_id: str, state: ChatSessionState) -> None:
        with self._guard:
            self._purge_expired(time.time())
            state.touch()
            self._sessions[session_id] = state

    def _purge_expired(self, now: float) -> None:
        expired_ids = [
            session_id
            for session_id, state in self._sessions.items()
            if now - state.last_activity_at > self._ttl_seconds
        ]
        for session_id in expired_ids:
            self._sessions.pop(session_id, None)


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
