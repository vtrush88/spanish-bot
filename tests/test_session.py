from session import advance


def test_correct_pops_no_requeue():
    q, retried = advance([1, 2, 3], [], remembered=True, giveup=False)
    assert q == [2, 3]
    assert retried == []


def test_wrong_attempt_requeues_once():
    q, retried = advance([1, 2, 3], [], remembered=False, giveup=False)
    assert q == [2, 3, 1]
    assert retried == [1]


def test_wrong_again_on_retry_does_not_requeue():
    # card 1 already retried; another miss must not re-append it
    q, retried = advance([1, 2], [1], remembered=False, giveup=False)
    assert q == [2]
    assert retried == [1]


def test_giveup_never_requeues():
    q, retried = advance([1, 2], [], remembered=False, giveup=True)
    assert q == [2]
    assert retried == []


def test_last_wrong_card_comes_back():
    q, retried = advance([5], [], remembered=False, giveup=False)
    assert q == [5]
    assert retried == [5]
