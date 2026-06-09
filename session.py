from __future__ import annotations

# Within-session queue policy (Option 2): a wrong *attempt* gets one more try at
# the end of the same session; an explicit give-up does not loop. The re-shown
# card is practice only — scheduling is driven by the first encounter (handled by
# the caller via the `retried` membership check), so a card is never re-queued twice.


def advance(
    queue: list[int],
    retried: list[int],
    *,
    remembered: bool,
    giveup: bool,
) -> tuple[list[int], list[int]]:
    """Pop the head card; re-append it once if it was a wrong attempt.

    Returns (new_queue, new_retried). A card is re-queued only when the answer
    was wrong (`not remembered`), it was not an explicit give-up, and the card
    hasn't already been retried this session.
    """
    head = queue[0]
    rest = queue[1:]
    new_retried = list(retried)
    if not remembered and not giveup and head not in retried:
        rest = rest + [head]
        new_retried.append(head)
    return rest, new_retried
