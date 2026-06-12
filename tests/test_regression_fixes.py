from __future__ import annotations

import json
import re

from ebook_app.epub.packaging import EPUBBuilder
from ebook_app.app.state.character_db import Character, CharacterDatabase


def test_epub_builder_writes_nav_namespace_overlay_and_unique_id(tmp_path):
    work_dir = tmp_path / "work"
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    builder = EPUBBuilder(
        title="Book",
        author="Author",
        output_dir=str(output_dir),
        work_dir=str(work_dir),
    )
    builder.add_chapter(
        filename="ch000.xhtml",
        title="Chapter 1",
        xhtml=(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="p1">Hello</p></body></html>'
        ),
    )

    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF....WAVE")
    builder.add_audio(
        chapter_filename="ch000.xhtml",
        audio_path=str(audio_file),
        segments=[{"paragraph_id": "p1", "clip_begin": 0.0, "clip_end": 1.0}],
    )

    builder.build()

    nav = (work_dir / "OEBPS" / "nav.xhtml").read_text(encoding="utf-8")
    opf = (work_dir / "OEBPS" / "content.opf").read_text(encoding="utf-8")

    assert 'xmlns:epub="http://www.idpf.org/2007/ops"' in nav
    assert 'media-overlay="ch000_smil"' in opf
    assert "urn:uuid:12345" not in opf
    assert "2025-01-01T00:00:00Z" not in opf
    assert re.search(r"urn:uuid:[0-9a-f-]{36}", opf)


def test_character_database_persists_to_json(tmp_path):
    db_path = tmp_path / "character_db.json"
    db = CharacterDatabase(path=db_path)
    db.add(Character(name="Alice", voice="af_heart", gender="female"))

    assert db_path.exists()

    loaded = CharacterDatabase(path=db_path)
    char = loaded.get("Alice")
    assert char is not None
    assert char.voice == "af_heart"

    loaded.remove("Alice")
    persisted = json.loads(db_path.read_text(encoding="utf-8"))
    assert persisted == []
