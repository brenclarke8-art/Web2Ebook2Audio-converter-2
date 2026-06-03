from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal

from ebook_app.services.llm_client import OllamaChatClient

SegmentType = Literal["dialogue", "thought", "narration", "general"]

_SEGMENTATION_SYSTEM_PROMPT = """You are a text‑segmentation and character‑extraction engine.
Your job is to analyze the provided novel text and output a STRICT JSON object.
Follow ALL rules exactly. Never add fields not defined here. Never hallucinate.

============================================================
GLOBAL RULES
============================================================
1. You MUST return valid JSON. No comments, no explanations, no prose.
2. You MUST segment the text in reading order.
3. You MUST NOT invent characters, genders, or speakers.
4. If uncertain, use "unknown" and reduce confidence.
5. You MUST preserve the original text exactly for each segment.
6. You MUST NOT merge or split sentences unless required by the rules below.
7. You MUST NOT infer emotions, motivations, or hidden meaning.

============================================================
SEGMENTATION RULES
============================================================
Segment the text into the following types:

- "dialogue" → text inside quotes spoken aloud by a character.
- "thought" → internal monologue, often italicized or marked with special brackets.
- "narration" → everything else.

Each segment MUST contain:
- the exact text
- the type
- the speaker (if known)
- the speaker_gender (if known)
- speaker_confidence (0–1)
- gender_confidence (0–1)
- character_confidence (0–1)
- paragraph_id (stable ID based on paragraph order)

============================================================
SPEAKER ATTRIBUTION RULES
============================================================
Assign a speaker ONLY when:
- the speaker is explicitly named in the same paragraph, OR
- the speaker is unambiguously the only possible character speaking.

If ambiguous:
- speaker = "unknown"
- speaker_confidence = 0.0

NEVER guess based on tone, personality, or narrative style.

============================================================
GENDER RULES
============================================================
Assign gender ONLY when:
- explicitly stated (he/she, boy/girl, man/woman)
- strongly implied by name with high certainty

If uncertain:
- speaker_gender = "unknown"
- gender_confidence = 0.0

============================================================
CHARACTER LIST RULES
============================================================
Extract ALL characters explicitly mentioned in the text.
For each character include:
- name
- gender (if known)
- gender_confidence (0–1)

Do NOT include:
- inferred characters
- unnamed characters ("the guard", "the teacher")

============================================================
JSON OUTPUT FORMAT
============================================================

{
  "characters": [
    {
      "name": "string",
      "gender": "male | female | unknown",
      "gender_confidence": 0.0
    }
  ],
  "segments": [
    {
      "paragraph_id": "p001",
      "text": "string",
      "type": "dialogue | thought | narration",
      "speaker": "string",
      "speaker_gender": "male | female | unknown",
      "speaker_confidence": 0.0,
      "gender_confidence": 0.0,
      "character_confidence": 0.0
    }
  ]
}

============================================================
BEGIN INPUT TEXT
============================================================
"""


@dataclass
class DialogueLLMSegment:
    text: str
    type: SegmentType
    speaker: str | None


@dataclass
class DialogueLLMResult:
    segments: list[DialogueLLMSegment]
    characters: list[Any]


class DialogueSegmentationService:
    _UI_NOISE_PATTERNS = (
        r"\bnext\s+chapter\b",
        r"\bprevious\s+chapter\b",
        r"\btable\s+of\s+contents\b",
        r"\bchapter\s+list\b",
        r"\bmenu\b",
        r"\bnavigation\b",
        r"\bskip\s+to\s+content\b",
        r"\bsubscribe\b",
        r"\blog[\s-]?in\b",
        r"\bsign[\s-]?in\b",
        r"\bsign[\s-]?up\b",
    )

    def __init__(self, *, client: OllamaChatClient, strict_quotes: bool = False) -> None:
        self.client = client
        self.strict_quotes = bool(strict_quotes)

    def parse(
        self,
        *,
        text: str,
        chapter_id: str,
        known_characters: list[str] | None = None,
    ) -> DialogueLLMResult:
        cleaned = self.clean_text_for_llm(text)
        if not cleaned:
            return DialogueLLMResult(
                segments=[DialogueLLMSegment(text="", type="narration", speaker="narrator")],
                characters=[],
            )

        payload = {
            "text": cleaned,
            "characters": [n for n in (known_characters or []) if isinstance(n, str) and n.strip()],
        }
        raw = self.client.ask_json(system=_SEGMENTATION_SYSTEM_PROMPT, user=payload, chapter_id=chapter_id)
        return self._normalize_payload(raw, source_text=cleaned)

    @classmethod
    def _is_noise_line(cls, line: str) -> bool:
        text = (line or "").strip()
        if not text:
            return False
        lowered = text.lower()
        if lowered.startswith(("http://", "https://", "www.")):
            return True
        if re.fullmatch(r"[^\w]{3,}", lowered):
            return True
        return any(re.search(pattern, lowered) for pattern in cls._UI_NOISE_PATTERNS)

    @classmethod
    def clean_text_for_llm(cls, text: str) -> str:
        source = (text or "").strip()
        if not source:
            return ""
        lines = [line.strip() for line in source.splitlines()]
        kept = [line for line in lines if line and not cls._is_noise_line(line)]
        if not kept:
            return source
        cleaned = "\n".join(kept)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned or source

    def _normalize_payload(self, payload: dict, *, source_text: str) -> DialogueLLMResult:
        raw_segments = payload.get("segments") if isinstance(payload, dict) else None
        segments: list[DialogueLLMSegment] = []
        characters: list[str] = []
        seen = set()

        if isinstance(payload, dict) and isinstance(payload.get("characters"), list):
            for item in payload["characters"]:
                if isinstance(item, str):
                    name = item.strip()
                    if name and name.casefold() != "narrator" and name.casefold() not in seen:
                        seen.add(name.casefold())
                        characters.append(name)
                elif isinstance(item, dict):
                    name = str(item.get("name", "")).strip()
                    if name and name.casefold() != "narrator" and name.casefold() not in seen:
                        confidence = item.get("confidence", 0.0)
                        try:
                            confidence_val = float(confidence)
                        except (TypeError, ValueError):
                            confidence_val = 0.0
                        seen.add(name.casefold())
                        characters.append(
                            {
                                "name": name,
                                "gender": str(item.get("gender", "unknown")).strip().lower() or "unknown",
                                "confidence": confidence_val,
                            }
                        )

        if isinstance(raw_segments, list):
            for item in raw_segments:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                seg_type = str(item.get("type", "narration")).strip().lower()
                if seg_type == "general":
                    seg_type = "narration"
                if seg_type not in {"dialogue", "thought", "narration"}:
                    seg_type = "narration"
                speaker_val = item.get("speaker")
                speaker = str(speaker_val).strip() if isinstance(speaker_val, str) else None
                if speaker and speaker.casefold() == "narrator":
                    speaker = "narrator"
                if seg_type == "narration" and not speaker:
                    speaker = "narrator"
                if self.strict_quotes and seg_type in {"dialogue", "thought"} and not self._looks_quoted(text):
                    seg_type = "narration"
                    speaker = "narrator"
                segments.append(DialogueLLMSegment(text=text, type=seg_type, speaker=speaker))
                if speaker and speaker.casefold() != "narrator" and speaker.casefold() not in seen:
                    seen.add(speaker.casefold())
                    characters.append(speaker)

        if not segments:
            segments = [DialogueLLMSegment(text=source_text, type="narration", speaker="narrator")]

        return DialogueLLMResult(segments=segments, characters=characters)

    @staticmethod
    def _looks_quoted(text: str) -> bool:
        clean = (text or "").strip()
        return (
            (len(clean) >= 2 and clean.startswith('"') and clean.endswith('"'))
            or (len(clean) >= 2 and clean.startswith("“") and clean.endswith("”"))
            or bool(re.search(r'"[^"\n]+"', clean))
        )
