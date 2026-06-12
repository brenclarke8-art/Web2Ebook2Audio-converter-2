# ebook_app/text/identify/type_classifier.py
from __future__ import annotations

import json
import requests
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class LLMClient:
    base_url: str
    model: str
    timeout: int = 120
    retries: int = 1

    def classify(self, prompt: str) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "prompt": prompt,
        }

        last_error = None

        for attempt in range(self.retries + 1):
            try:
                resp = requests.post(
                    self.base_url,
                    json=payload,
                    timeout=self.timeout
                )
                resp.raise_for_status()

                data = resp.json()

                if isinstance(data, dict) and "response" in data:
                    try:
                        return json.loads(data["response"])
                    except Exception:
                        return {}

                if isinstance(data, dict):
                    return data

                return {}

            except Exception as exc:
                last_error = str(exc)
                if attempt >= self.retries:
                    break

        return {}


class Pass2Classifier:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def classify_segment(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        text = str(segment.get("text", "")).strip()
        context_before = str(segment.get("context_before", "")).strip()
        context_after = str(segment.get("context_after", "")).strip()
        is_dialogue_candidate = bool(segment.get("is_dialogue_candidate", False))

        prompt = self._build_prompt(
            text=text,
            context_before=context_before,
            context_after=context_after,
            is_dialogue_candidate=is_dialogue_candidate,
        )

        fallback = {
            "type": "narration",
            "speaker": "narrator",
            "gender": "unknown",
            "speaker_confidence": 0.0,
            "gender_confidence": 0.0,
            "character_confidence": 0.0,
        }

        try:
            raw = self.llm_client.classify(prompt)
            result = self._sanitize_llm_output(raw, fallback)
        except Exception:
            result = fallback

        classified = dict(segment)
        classified.update(result)

        # Ensure required fields exist
        classified.setdefault("type", "narration")
        classified.setdefault("speaker", "narrator")
        classified.setdefault("gender", "unknown")
        classified.setdefault("speaker_confidence", 0.0)
        classified.setdefault("gender_confidence", 0.0)
        classified.setdefault("character_confidence", 0.0)

        return classified

    def _build_prompt(
        self,
        text: str,
        context_before: str,
        context_after: str,
        is_dialogue_candidate: bool,
    ) -> str:
        hint = "true" if is_dialogue_candidate else "false"

        return (
            "You are a semantic classifier for novel text.\n"
            "Classify the given segment into one of: dialogue, thought, narration.\n"
            "Also identify the most likely speaker name (or 'narrator' or 'unknown'), "
            "and the speaker's gender (male, female, unknown).\n"
            "Return ONLY a JSON object with keys: type, speaker, gender, "
            "speaker_confidence, gender_confidence, character_confidence.\n\n"
            f"Context before:\n{context_before}\n\n"
            f"Segment:\n{text}\n\n"
            f"Context after:\n{context_after}\n\n"
            f"Dialogue candidate hint: {hint}\n"
        )

    def _sanitize_llm_output(
        self,
        raw: Any,
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            return fallback

        out = {}

        out["type"] = str(raw.get("type", fallback["type"])).strip().lower()
        if out["type"] not in {"dialogue", "thought", "narration"}:
            out["type"] = fallback["type"]

        out["speaker"] = str(raw.get("speaker", fallback["speaker"])).strip() or fallback["speaker"]

        out["gender"] = str(raw.get("gender", fallback["gender"])).strip().lower()
        if out["gender"] not in {"male", "female", "unknown"}:
            out["gender"] = "unknown"

        def _num(val, default):
            try:
                return float(val)
            except Exception:
                return default

        out["speaker_confidence"] = _num(raw.get("speaker_confidence"), fallback["speaker_confidence"])
        out["gender_confidence"] = _num(raw.get("gender_confidence"), fallback["gender_confidence"])
        out["character_confidence"] = _num(raw.get("character_confidence"), fallback["character_confidence"])

        return out
