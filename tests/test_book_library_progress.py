from __future__ import annotations

from ebook_app.app.state.book_library import BookLibrary


def test_book_library_persists_inventory_and_last_processed(tmp_path):
    library = BookLibrary(tmp_path)
    book_id = library.add_book("My Book", "Author", "https://example.com/index")

    library.update_inventory(book_id, raw_chapter_count=120, valid_chapter_count=100)
    library.update_last_processed(book_id, last_processed_chapter=45)

    entry = library.get_book(book_id)
    assert entry is not None
    assert entry["raw_chapter_count"] == 120
    assert entry["valid_chapter_count"] == 100
    assert entry["last_chapter_count"] == 100
    assert entry["last_processed_chapter"] == 45
    assert entry["last_checked"] is not None
    assert entry["last_converted"] is not None
