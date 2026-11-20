import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime


@dataclass(frozen=True)
class Window:
    """At most `limit` hits within the last `seconds`."""

    limit: int
    seconds: float


FAMILY_CREATE_WINDOWS = (Window(3, 3600), Window(10, 86400))
INVITE_ACCEPT_WINDOWS = (Window(30, 3600),)


class WindowLimiter:
    """In-memory sliding-window limiter keyed by an opaque string.

    The keys (client addresses) live only in this process; a restart forgets them by design.
    Memory is bounded: at most `max_keys` keys (the least recently used is evicted) and, per key,
    at most the largest window limit of hits. Idle keys are dropped at most once per
    `sweep_every` seconds.
    """

    def __init__(
        self,
        windows: tuple[Window, ...] | list[Window],
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
        sweep_every: float = 60.0,
    ) -> None:
        self._windows = tuple(windows)
        self._clock = clock
        self._max_keys = max_keys
        self._sweep_every = sweep_every
        self._longest = max(w.seconds for w in self._windows)
        self._swept_at = clock()
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, key: str) -> bool:
        """Record a hit and return True, or return False (recording nothing) when over a window."""
        now = self._clock()
        if now - self._swept_at >= self._sweep_every:
            self._sweep(now)
        hits = self._hits.get(key)
        if hits is None:
            hits = self._hits[key] = deque()
            if len(self._hits) > self._max_keys:
                self._hits.popitem(last=False)
        else:
            self._hits.move_to_end(key)
        while hits and hits[0] <= now - self._longest:
            hits.popleft()
        for window in self._windows:
            if sum(1 for t in hits if t > now - window.seconds) >= window.limit:
                return False
        hits.append(now)
        return True

    def tracked_keys(self) -> int:
        return len(self._hits)

    def _sweep(self, now: float) -> None:
        """Keys are ordered by last use, so the idle ones are all at the front."""
        self._swept_at = now
        while self._hits:
            hits = self._hits[next(iter(self._hits))]
            if hits and hits[-1] > now - self._longest:
                break
            self._hits.popitem(last=False)


class DailyCounter:
    """Families created and then erased within the current UTC day, as seen by this process.

    The database counts live families only, so erasing a family would free its place for the
    day; adding it here keeps the place taken. A restart forgets the tally (live rows still count).
    """

    def __init__(self, today: Callable[[], date] = lambda: datetime.now(UTC).date()) -> None:
        self._today = today
        self._day = today()
        self._n = 0

    def add(self) -> None:
        self.count()
        self._n += 1

    def count(self) -> int:
        if (day := self._today()) != self._day:
            self._day, self._n = day, 0
        return self._n
