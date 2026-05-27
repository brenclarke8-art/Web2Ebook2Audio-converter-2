#!/usr/bin/env python3
"""
Per-book character database for dialogue detection hints.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BookCharacterDatabase:
    """Stores and retrieves character data per book in output/character_db."""

    def __init__(self, output_dir: str):
        self.base_dir = Path(output_dir) / "character_db"

    @staticmethod
    def _safe_book_key(book_title: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (book_title or "").strip())
        cleaned = cleaned.strip("._")
        return cleaned or "book"

    def _book_db_path(self, book_title: str) -> Path:
        return self.base_dir / f"{self._safe_book_key(book_title)}.json"

    def _read_payload(self, book_title: str) -> Dict:
        path = self._book_db_path(book_title)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read character DB %s: %s", path, exc)
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _normalize_record(entry: Dict) -> Dict:
        name = str(entry.get("name", "")).strip()
        if not name:
            return {}

        gender = str(entry.get("gender", "unknown")).strip().lower() or "unknown"
        if gender not in {"male", "female", "neutral", "unknown"}:
            gender = "unknown"

        def _to_int(value) -> int:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return 0

        return {
            "name": name,
            "gender": gender,
            "dialogue_count": _to_int(entry.get("dialogue_count", 0)),
            "mention_count": _to_int(entry.get("mention_count", 0)),
        }

    def load_records(self, book_title: str) -> List[Dict]:
        data = self._read_payload(book_title)
        if not data:
            return []

        if isinstance(data, dict):
            entries = data.get("characters", [])
        elif isinstance(data, list):
            entries = data
        else:
            entries = []

        records: List[Dict] = []
        for entry in entries:
            if isinstance(entry, dict):
                normalized = self._normalize_record(entry)
                if normalized:
                    records.append(normalized)
        return records

    def load_review_decisions(self, book_title: str) -> Dict:
        data = self._read_payload(book_title)
        raw = data.get("review_decisions", {}) if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            return {"rename_aliases": [], "gender_overrides": []}

        rename_aliases: List[Dict[str, str]] = []
        for item in raw.get("rename_aliases", []):
            if not isinstance(item, dict):
                continue
            src = str(item.get("from", "")).strip()
            dest = str(item.get("to", "")).strip()
            if src and dest and src.casefold() != dest.casefold():
                rename_aliases.append({"from": src, "to": dest})

        gender_overrides: List[Dict[str, str]] = []
        for item in raw.get("gender_overrides", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            gender = str(item.get("gender", "unknown")).strip().lower() or "unknown"
            if not name or gender not in {"male", "female", "neutral", "unknown"}:
                continue
            gender_overrides.append({"name": name, "gender": gender})

        return {
            "rename_aliases": rename_aliases,
            "gender_overrides": gender_overrides,
        }

    def load_character_names(self, book_title: str) -> List[str]:
        names = {record["name"] for record in self.load_records(book_title) if record.get("name")}
        return sorted(names)

    def save_characters(
        self,
        book_title: str,
        characters: List[Dict],
        review_decisions: Optional[Dict] = None,
    ) -> Path:
        merged: Dict[str, Dict] = {}

        for record in self.load_records(book_title):
            key = record["name"].casefold()
            merged[key] = dict(record)

        for entry in characters:
            if not isinstance(entry, dict):
                continue
            record = self._normalize_record(entry)
            if not record:
                continue

            key = record["name"].casefold()
            if key not in merged:
                merged[key] = record
                continue

            existing = merged[key]
            if existing.get("gender", "unknown") == "unknown" and record["gender"] != "unknown":
                existing["gender"] = record["gender"]
            existing["dialogue_count"] = max(existing.get("dialogue_count", 0), record["dialogue_count"])
            existing["mention_count"] = max(existing.get("mention_count", 0), record["mention_count"])

        final_records = sorted(
            merged.values(),
            key=lambda item: (item["dialogue_count"], item["mention_count"], item["name"]),
            reverse=True,
        )

        existing_decisions = self.load_review_decisions(book_title)
        new_decisions = review_decisions if isinstance(review_decisions, dict) else {}
        merged_rename_aliases: Dict[str, Dict[str, str]] = {}
        for item in existing_decisions.get("rename_aliases", []):
            merged_rename_aliases[item["from"].casefold()] = dict(item)
        for item in new_decisions.get("rename_aliases", []):
            if not isinstance(item, dict):
                continue
            src = str(item.get("from", "")).strip()
            dest = str(item.get("to", "")).strip()
            if not src or not dest or src.casefold() == dest.casefold():
                continue
            merged_rename_aliases[src.casefold()] = {"from": src, "to": dest}

        merged_gender_overrides: Dict[str, Dict[str, str]] = {}
        for item in existing_decisions.get("gender_overrides", []):
            merged_gender_overrides[item["name"].casefold()] = dict(item)
        for item in new_decisions.get("gender_overrides", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            gender = str(item.get("gender", "unknown")).strip().lower() or "unknown"
            if not name or gender not in {"male", "female", "neutral", "unknown"}:
                continue
            merged_gender_overrides[name.casefold()] = {"name": name, "gender": gender}

        payload = {
            "book": book_title,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "characters": final_records,
            "review_decisions": {
                "rename_aliases": sorted(
                    merged_rename_aliases.values(),
                    key=lambda item: (item["from"].casefold(), item["to"].casefold()),
                ),
                "gender_overrides": sorted(
                    merged_gender_overrides.values(),
                    key=lambda item: item["name"].casefold(),
                ),
            },
        }

        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self._book_db_path(book_title)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
