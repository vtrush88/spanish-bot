import formatting


def test_card_preview_includes_all_fields():
    text = formatting.card_preview({
        "spanish": "comida", "russian": "еда", "transcription": "комИда",
        "example_es": "La comida está lista.", "example_ru": "Еда готова.",
    })
    assert "comida" in text
    assert "еда" in text
    assert "комИда" in text
    assert "La comida está lista." in text


def test_answer_reveal():
    text = formatting.answer_reveal({"russian": "еда", "transcription": "комИда"})
    assert "еда" in text and "комИда" in text


def test_word_list_line_numbered():
    line = formatting.word_list_line(3, {"spanish": "agua", "russian": "вода"})
    assert line.startswith("3.")
    assert "agua" in line and "вода" in line


def test_vocab_title_single_page():
    assert formatting.vocab_title(0, 1, 4) == "📖 Твой словарь (4 слова)"


def test_vocab_title_multi_page():
    assert formatting.vocab_title(1, 3, 12) == "📖 Твой словарь (стр. 2/3, 12 слов)"


def test_vocab_title_plural_forms():
    assert formatting.vocab_title(0, 1, 1).endswith("(1 слово)")
    assert formatting.vocab_title(0, 1, 21).endswith("(21 слово)")
    assert formatting.vocab_title(0, 1, 3).endswith("(3 слова)")
    assert formatting.vocab_title(0, 3, 11).endswith("11 слов)")
