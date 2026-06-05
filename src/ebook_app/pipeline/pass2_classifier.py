# src/ebook_app/pipeline/pass2_classifier.py
"""
Pass‑2 Classifier
-----------------
LLM-based semantic classification of segments produced by Pass‑1.

Input (from Pass‑1):
    {
        "text": "...",
        "paragraph_id": 12,
        "context_before": "...",
        "context_after": "...",
        "is_dialogue_candidate": true/false
    }

Output (per segment, plain dict):
    {
        # Original Pass‑1 fields preserved
        "text": "...",
        "paragraph_id": 12,
        "context_before": "...",
        "context_after": "...",
        "is_dialogue_candidate": true/false,

        # Pass‑2 fields added
        "type": "dialogue" | "thought" | "narration",
        "speaker": "Alice",
        "gender": "female" | "male" | "unknown",
        "speaker_confidence": 0.92,
        "gender_confidence": 0.88,
        "character_confidence": 0.90,
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Any


# ---------------------------------------------------------------------------
# LLM Client Contract
# ---------------------------------------------------------------------------

@dataclass
class LLMClient:
    """
    Minimal HTTP JSON client for Pass‑2 classification.

    Expected server API:
        POST {base_url}
        {
            "model": "<model-name>",
            "prompt": "<prompt>"
        }

    Expected response:
        {
            "type": "...",
            "speaker": "...",
            "gender": "...",
            "speaker_confidence": 0.0–1.0,
            "gender_confidence": 0.0–1.0,
            "character_confidence": 0.0–1.0
        }
    """

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

                # If the server returns {"response": "...json..."}
                if isinstance(data, dict) and "response" in data:
                    try:
                        return json.loads(data["response"])
                    except Exception:
                        return {}

                # If the server returns the JSON object directly
                if isinstance(data, dict):
                    return data

                return {}

            except Exception as exc:
                last_error = str(exc)
                if attempt >= self.retries:
                    break

        # If all retries fail, return empty dict
        return {}


# ---------------------------------------------------------------------------
# Pass‑2 Classifier
# ---------------------------------------------------------------------------

class Pass2Classifier:
    """
    Second-pass classifier: uses an LLM to assign semantic labels
    (type, speaker, gender, confidences) to each segment.

    It is deliberately stateless; all state is managed by the controller.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_segment(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify a single segment using the LLM.

        Returns a dict that preserves ALL Pass‑1 fields and adds Pass‑2 fields.
        """
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

        # Default safe fallback
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

        # Merge original Pass‑1 fields with Pass‑2 classification
        classified = dict(segment)
        classified.update(result)

        # Ensure paragraph_id is int
        try:
            classified["paragraph_id"] = int(classified.get("paragraph_id", -1))
        except Exception:
            classified["paragraph_id"] = -1

        return classified

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        text: str,
        context_before: str,
        context_after: str,
        is_dialogue_candidate: bool,
    ) -> str:
        """
        Build a classification prompt for the LLM.
        """
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

    # ------------------------------------------------------------------
    # Output sanitization
    # ------------------------------------------------------------------

    def _sanitize_llm_output(
        self,
        raw: Any,
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Ensure the LLM output is a valid dict with required fields.
        """
        if not isinstance(raw, dict):
            return fallback

        out = {}

        # Required string fields
        out["type"] = str(raw.get("type", fallback["type"])).strip().lower()
        if out["type"] not in {"dialogue", "thought", "narration"}:
            out["type"] = fallback["type"]

        out["speaker"] = str(raw.get("speaker", fallback["speaker"])).strip() or fallback["speaker"]
        out["gender"] = str(raw.get("gender", fallback["gender"])).strip().lower()
        if out["gender"] not in {"male", "female", "unknown"}:
            out["gender"] = "unknown"

        # Confidence fields
        def _num(val, default):
            try:
                return float(val)
            except Exception:
                return default

        out["speaker_confidence"] = _num(raw.get("speaker_confidence"), fallback["speaker_confidence"])
        out["gender_confidence"] = _num(raw.get("gender_confidence"), fallback["gender_confidence"])
        out["character_confidence"] = _num(raw.get("character_confidence"), fallback["character_confidence"])

        return out
