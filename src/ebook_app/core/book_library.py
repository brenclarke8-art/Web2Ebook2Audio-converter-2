from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _slugify(value: str) -> str:
    cleaned = ''.join(ch.lower() if ch.isalnum() else '-' for ch in (value or '').strip())
    cleaned = '-'.join(part for part in cleaned.split('-') if part)
    return cleaned or 'book'


class BookLibrary:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.root_dir / 'book_library.json'
        self._data = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError, TypeError):
            return {}
        if isinstance(payload, dict):
            return {str(k): v for k, v in payload.items() if isinstance(v, dict)}
        return {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding='utf-8')

    def add_book(self, title: str, author: str, index_url: str) -> str:
        book_id = f"{_slugify(title)}-{uuid4().hex[:8]}"
        timestamp = _now_iso()
        self._data[book_id] = {
            'book_id': book_id,
            'title': title,
            'author': author,
            'index_url': index_url,
            'raw_chapter_count': 0,
            'valid_chapter_count': 0,
            'last_chapter_count': 0,
            'last_processed_chapter': 0,
            'created_at': timestamp,
            'last_checked': None,
            'last_converted': None,
        }
        self._save()
        return book_id

    def get_book(self, book_id: str) -> dict | None:
        entry = self._data.get(book_id)
        return dict(entry) if entry else None

    def list_books(self) -> list[dict]:
        return [dict(item) for item in self._data.values()]

    def remove_book(self, book_id: str) -> bool:
        if book_id not in self._data:
            return False
        del self._data[book_id]
        self._save()
        return True

    def update_inventory(self, book_id: str, *, raw_chapter_count: int, valid_chapter_count: int) -> None:
        entry = self._data.get(book_id)
        if not entry:
            return
        timestamp = _now_iso()
        entry['raw_chapter_count'] = max(0, int(raw_chapter_count))
        entry['valid_chapter_count'] = max(0, int(valid_chapter_count))
        entry['last_chapter_count'] = entry['valid_chapter_count']
        entry['last_checked'] = timestamp
        entry['last_converted'] = timestamp
        self._save()

    def update_last_processed(self, book_id: str, last_processed_chapter: int) -> None:
        entry = self._data.get(book_id)
        if not entry:
            return
        entry['last_processed_chapter'] = max(0, int(last_processed_chapter))
        entry['last_converted'] = _now_iso()
        self._save()
