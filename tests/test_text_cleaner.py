from ebook_app.models.scraper.text_cleaner import TextCleaner


def test_clean_text_removes_reader_control_block() -> None:
    raw = (
        "Intro line\n"
        "RAWS\nTranslate\nForum\nReader settings\nText\nA−\nA+\nCompact\nNormal\nWide\n"
        "Theme\nDark\nSepia\nLight\nWidth\nCompact\nDefault\nWide\nTools\nBottom\nTop\n"
        "Reset\nReport bug\n"
        "Actual chapter line."
    )
    cleaned = TextCleaner.clean_text(raw)
    assert "RAWS" not in cleaned
    assert "Reader settings" not in cleaned
    assert "Report bug" not in cleaned
    assert "Intro line" in cleaned
    assert "Actual chapter line." in cleaned


def test_clean_text_keeps_regular_text_when_control_count_is_low() -> None:
    raw = "The sky turned dark.\nTheme of the story is growth.\nA normal paragraph."
    cleaned = TextCleaner.clean_text(raw)
    assert cleaned == raw
