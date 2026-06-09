import keyboards


def test_main_menu_has_all_buttons():
    kb = keyboards.main_menu()
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert keyboards.BTN_ADD in labels
    assert keyboards.BTN_FLASHCARDS in labels
    assert keyboards.BTN_TRANSLATE in labels
    assert keyboards.BTN_LISTEN in labels
    assert keyboards.BTN_VOCAB in labels


def test_reveal_keyboard_has_callback_data():
    kb = keyboards.reveal_keyboard()
    datas = {btn.callback_data for row in kb.inline_keyboard for btn in row}
    assert "show_answer" in datas


def test_grade_keyboard_has_remember_and_forgot():
    kb = keyboards.grade_keyboard()
    datas = {btn.callback_data for row in kb.inline_keyboard for btn in row}
    assert "grade:remember" in datas
    assert "grade:forgot" in datas
