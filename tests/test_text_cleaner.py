from ebook_app.text.parse.html_cleaner import TextCleaner


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


def test_remove_site_navigation_strips_back_link() -> None:
    raw = "← Back to novel\nThe chapter begins here."
    cleaned = TextCleaner.clean_text(raw)
    assert "← Back to novel" not in cleaned
    assert "The chapter begins here." in cleaned


def test_remove_site_navigation_strips_reader_mode_hint() -> None:
    raw = "Reader mode with saved preferences, scroll memory and mobile navigation.\nOnce upon a time."
    cleaned = TextCleaner.clean_text(raw)
    assert "Reader mode" not in cleaned
    assert "Once upon a time." in cleaned


def test_remove_site_navigation_strips_bare_chapter_number() -> None:
    raw = "Chapter 487\nChapter 486: Roman -3-\nThump. Thump. Thump."
    cleaned = TextCleaner.clean_text(raw)
    # Bare "Chapter 487" is navigation noise → stripped
    assert "Chapter 487\n" not in cleaned
    assert cleaned.startswith("Chapter 487") is False
    # Chapter title with subtitle is story content → kept
    assert "Chapter 486: Roman -3-" in cleaned
    assert "Thump. Thump. Thump." in cleaned
