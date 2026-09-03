"""Replay clock: a virtual 'today' that walks through the station file during the pitch.

When inactive every consumer uses the real date.  ``POST /admin/replay/start`` activates it,
``/step`` advances it, ``/reset`` returns to real time.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from datetime import date, timedelta


@dataclass
class ReplayState:
    active: bool = False
    current: date | None = None
    start_date: date | None = None
    step_days: int = 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["today"] = (self.current or date.today()).isoformat()
        d["current"] = self.current.isoformat() if self.current else None
        d["start_date"] = self.start_date.isoformat() if self.start_date else None
        return d


class ReplayClock:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = ReplayState()

    @property
    def state(self) -> ReplayState:
        with self._lock:
            return ReplayState(**asdict(self._state))

    def today(self) -> date:
        with self._lock:
            return self._state.current if self._state.active and self._state.current else date.today()

    def start(self, start_date: date, step_days: int = 1) -> ReplayState:
        with self._lock:
            self._state = ReplayState(active=True, current=start_date, start_date=start_date, step_days=max(1, step_days))
            return ReplayState(**asdict(self._state))

    def step(self, steps: int = 1, until: date | None = None) -> ReplayState:
        with self._lock:
            if not self._state.active or self._state.current is None:
                raise RuntimeError("replay is not active - call start first")
            nxt = self._state.current + timedelta(days=self._state.step_days * max(1, steps))
            if until and nxt > until:
                nxt = until
            self._state.current = nxt
            return ReplayState(**asdict(self._state))

    def reset(self) -> ReplayState:
        with self._lock:
            self._state = ReplayState()
            return ReplayState(**asdict(self._state))


replay_clock = ReplayClock()
