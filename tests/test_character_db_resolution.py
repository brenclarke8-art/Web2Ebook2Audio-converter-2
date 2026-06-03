from __future__ import annotations

import json

from ebook_app.models.character_db import Character, CharacterDatabase


def test_character_database_resolves_normalized_and_alias_names(tmp_path):
    db = CharacterDatabase(path=tmp_path / "character_db.json")
    db.add(Character(name="Alice", voice="af_heart", gender="female", aliases=["Lady Alice"]))

    assert db.resolve_name(" alice ") is not None
    assert db.resolve_name("Alice.") is not None
    resolved_alias = db.resolve_name("Lady Alice")
    assert resolved_alias is not None
    assert resolved_alias.name == "Alice"


def test_character_database_loads_without_aliases_and_saves_with_aliases_key(tmp_path):
    db_path = tmp_path / "character_db.json"
    db_path.write_text(
        json.dumps([{"name": "Alice", "voice": "af_heart", "gender": "female", "description": ""}]),
        encoding="utf-8",
    )

    db = CharacterDatabase(path=db_path)
    loaded = db.get("Alice")
    assert loaded is not None
    assert loaded.aliases == []

    db.save()
    payload = json.loads(db_path.read_text(encoding="utf-8"))
    assert payload[0]["aliases"] == []
