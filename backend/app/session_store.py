"""Session storage abstraction.

Session state (portfolio holdings + chat history) is kept behind a small
interface so the default in-process implementation can be swapped for a
shared backend (e.g. Redis) without touching callers in agent.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from cachetools import TTLCache


@dataclass
class PortfolioSession:
    session_id: str
    holdings: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)


class SessionStore(ABC):
    """Interface for storing PortfolioSession objects by session_id."""

    @abstractmethod
    def get(self, session_id: str) -> PortfolioSession | None:
        ...

    @abstractmethod
    def set(self, session_id: str, session: PortfolioSession) -> None:
        ...

    @abstractmethod
    def delete(self, session_id: str) -> None:
        ...


class InMemorySessionStore(SessionStore):
    """Default implementation: a bounded, TTL-evicted in-process cache.

    Max 500 concurrent sessions, evicted after 1 hour of inactivity.
    Prevents memory exhaustion from abandoned or maliciously opened sessions.
    Not shared across worker processes — swap in a Redis-backed SessionStore
    before scaling horizontally.
    """

    def __init__(self, maxsize: int = 500, ttl: int = 3600):
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

    def get(self, session_id: str) -> PortfolioSession | None:
        return self._cache.get(session_id)

    def set(self, session_id: str, session: PortfolioSession) -> None:
        self._cache[session_id] = session

    def delete(self, session_id: str) -> None:
        self._cache.pop(session_id, None)
