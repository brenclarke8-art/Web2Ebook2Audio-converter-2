# ebook_app/text/identify/character_db_updater.py
from __future__ import annotations
from typing import List, Dict


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    return (
        name.strip()
            .lower()
            .replace(".", "")
            .replace(",", "")
            .replace("  ", " ")
    )


class CharacterMerger:
    """
    Build a canonical character database from Pass‑2 segments.

    Input: list of segments with at least:
        - speaker
        - gender

    Output: list[dict] with:
        {
            "name": str,
            "gender": "male" | "female" | "unknown",
            "voice": str,        # usually empty here
            "aliases": list[str]
        }
    """

    def merge(self, segments: List[Dict]) -> List[Dict]:
        by_key: Dict[str, Dict] = {}

        for seg in segments:
            speaker = str(seg.get("speaker", "") or "").strip()
            if not speaker:
                continue
            if speaker.lower() in {"narrator", "unknown"}:
                continue

            gender = str(seg.get("gender", "unknown") or "unknown").lower()
            norm = _normalize_name(speaker)
            if not norm:
                continue

            entry = by_key.get(norm)
            if entry is None:
                by_key[norm] = {
                    "name": speaker,
                    "gender": gender if gender in {"male", "female", "unknown"} else "unknown",
                    "voice": "",
                    "aliases": [],
                }
            else:
                # If we see a different spelling, add as alias
                if speaker != entry["name"] and speaker not in entry["aliases"]:
                    entry["aliases"].append(speaker)

                # Upgrade gender if we move from unknown → known
                if entry["gender"] == "unknown" and gender in {"male", "female"}:
                    entry["gender"] = gender

        return list(by_key.values())
