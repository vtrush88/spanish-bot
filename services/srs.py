from __future__ import annotations

from datetime import date, timedelta

LADDER = [1, 3, 7, 14, 30, 60]


def next_interval(current: int, remembered: bool) -> int:
    """Leitner ladder. Remembered → next rung > current (capped). Forgot → reset to 1."""
    if not remembered:
        return LADDER[0]
    for rung in LADDER:
        if rung > current:
            return rung
    return LADDER[-1]


def due_on(today: date, interval_days: int) -> date:
    return today + timedelta(days=interval_days)
