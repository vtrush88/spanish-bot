import formatting


def test_card_preview_includes_all_fields():
    text = formatting.card_preview({
        "word": "comida", "translation": "еда", "transcription": "комИда",
        "example": "La comida está lista.", "example_translation": "Еда готова.",
    })
    assert "comida" in text
    assert "еда" in text
    assert "комИда" in text
    assert "La comida está lista." in text


def test_card_preview_bolds_spanish_word():
    text = formatting.card_preview({
        "word": "comida", "translation": "еда", "transcription": "комИда",
        "example": "La comida está lista.", "example_translation": "Еда готова.",
    })
    assert "<b>comida</b>" in text


def test_card_preview_escapes_html_special_chars():
    # Raw <, >, & in the data must be escaped, or Telegram's HTML parser breaks.
    text = formatting.card_preview({
        "word": "tú & yo", "translation": "ты <и> я", "transcription": "ту и йо",
        "example": "a < b & c", "example_translation": "пример",
    })
    assert "<b>tú &amp; yo</b>" in text   # word escaped, then bolded
    assert "ты &lt;и&gt; я" in text
    assert "a &lt; b &amp; c" in text


def test_answer_reveal():
    text = formatting.answer_reveal({"translation": "еда", "transcription": "комИда"})
    assert "еда" in text and "комИда" in text


def test_word_list_line_numbered():
    line = formatting.word_list_line(3, {"word": "agua", "translation": "вода"})
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
