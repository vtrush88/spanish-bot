from datetime import date

from services import srs


def test_new_card_remembered_goes_to_first_rung():
    assert srs.next_interval(0, remembered=True) == 1


def test_remembered_climbs_ladder():
    assert srs.next_interval(1, remembered=True) == 3
    assert srs.next_interval(3, remembered=True) == 7
    assert srs.next_interval(7, remembered=True) == 14
    assert srs.next_interval(14, remembered=True) == 30
    assert srs.next_interval(30, remembered=True) == 60


def test_remembered_caps_at_max():
    assert srs.next_interval(60, remembered=True) == 60


def test_not_remembered_resets_to_one():
    assert srs.next_interval(30, remembered=False) == 1
    assert srs.next_interval(0, remembered=False) == 1


def test_due_on_adds_interval_days():
    assert srs.due_on(date(2026, 6, 3), 7) == date(2026, 6, 10)
