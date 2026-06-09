from __future__ import annotations

# Substrings that signal "I don't know / can't recall" — matched anywhere in
# the answer so phrases like "ой, не помню это слово" are caught too.
_GIVEUP_SUBSTRINGS = ("не помн", "непомн", "не зна", "незна", "не понима")

# Short stand-alone give-up answers (matched after trimming punctuation).
_GIVEUP_EXACT = {"хз", "забыла", "забыл", "пас", "пропустить", "дальше"}


def is_giveup(text: str) -> bool:
    """True if the learner signalled they don't know / can't recall the answer."""
    t = text.strip().lower()
    if not t:
        return False
    if any(s in t for s in _GIVEUP_SUBSTRINGS):
        return True
    return t.rstrip("?.!,) (") in _GIVEUP_EXACT
