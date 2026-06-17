from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

from ebook_app.app.state.character_db import CharacterDatabase
from ebook_app.text.parse.html_cleaner import TextCleaner
from ebook_app.text.segment.segmenter import DialogueSegmentationService


class OllamaChatClient:
    """
    Lightweight, tolerant Ollama client wrapper.

    - Supports both /api/chat and /api/generate endpoints.
    - Forces JSON output when possible (format: "json").
    - Robust JSON extraction from fenced or noisy responses.
    - Per-chapter JSONL logging when llm_log_path is provided.
    - Retries with small backoff; surfaces errors to caller on final failure.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434/api/generate",
        model: str = "qwen2.5-coder:7b",
        max_context_tokens: int = 250_000,
        timeout: int = 300,
        retries: int = 1,
        llm_log_path: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_context_tokens = int(max_context_tokens)
        self.timeout = int(timeout)
        # ensure at least one attempt
        self.retries = max(1, int(retries))
        self.llm_log_path = Path(llm_log_path) if llm_log_path else None

    # -------------------------
    # Logging
    # -------------------------
    def _log(self, record: dict[str, Any]) -> None:
        if not self.llm_log_path:
            return
        try:
            self.llm_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.llm_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            # Never raise from logging
            pass

    # -------------------------
    # JSON extraction helpers
    # -------------------------
    @staticmethod
    def _parse_json_text(raw: Any) -> Any:
        """
        Tolerant JSON extractor:
        - If raw is already dict/list, return it.
        - Strip fenced code blocks.
        - Try direct json.loads.
        - Try to extract first {...} or [...] substring.
        - On failure, raise ValueError to let caller handle retry/logging.
        """
        if isinstance(raw, (dict, list)):
            return raw

        text = "" if raw is None else str(raw).strip()

        # Remove leading/trailing code fences ``` or ```json
        if text.startswith("```"):
            lines = text.splitlines()
            # drop fence lines
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Try direct JSON
        try:
            return json.loads(text)
        except Exception:
            pass

        # Try to extract first JSON object or array
        obj_start = text.find("{")
        arr_start = text.find("[")
        # choose earliest non-negative start
        starts = [i for i in (obj_start, arr_start) if i != -1]
        if starts:
            start = min(starts)
            # find matching end (naive: last } or ])
            if text.rfind("}") != -1 and (text.rfind("}") > text.rfind("]")):
                end = text.rfind("}")
            else:
                end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                snippet = text[start : end + 1]
                try:
                    return json.loads(snippet)
                except Exception:
                    pass

        # If nothing worked, raise to allow retry logic to log the raw text
        raise ValueError("Unable to parse JSON from LLM response")

    # -------------------------
    # Internal payload builder
    # -------------------------
    def _build_payload_and_url(self, system: str, user: str) -> tuple[dict[str, Any], str, dict[str, str]]:
        """
        Build a payload appropriate for the endpoint in base_url.
        Supports:
          - Ollama /api/chat (preferred)
          - Ollama /api/generate
        If base_url already points to a specific endpoint, use it directly.
        """
        url = self.base_url
        headers: dict[str, str] = {"Content-Type": "application/json"}

        # Normalize: if user passed a base that ends with /api/chat or /api/generate, use it.
        if url.endswith("/api/chat"):
            # Ollama chat endpoint expects messages
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0, "num_ctx": min(self.max_context_tokens, 8192)},
            }
            return payload, url, headers

        if url.endswith("/api/generate"):
            # Ollama generate endpoint: prompt + options
            prompt = f"{system.strip()}\n\n{user.strip()}\n\nRespond ONLY with valid JSON. No commentary, no markdown."
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0, "num_ctx": min(self.max_context_tokens, 8192)},
            }
            return payload, url, headers

        # If base_url is just host (e.g., http://127.0.0.1:11434), prefer /api/chat
        if url.endswith("11434") or url.endswith("11434:11434") or url.endswith(":11434"):
            chat_url = url + "/api/chat"
            prompt_payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0, "num_ctx": min(self.max_context_tokens, 8192)},
            }
            return prompt_payload, chat_url, headers

        # Fallback: assume generate-like endpoint at provided url
        prompt = f"{system.strip()}\n\n{user.strip()}\n\nRespond ONLY with valid JSON. No commentary, no markdown."
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_ctx": min(self.max_context_tokens, 8192)},
        }
        return payload, url, headers

    # -------------------------
    # Public ask methods
    # -------------------------
    def ask_json_any(self, *, system: str, user: str, chapter_id: str) -> Any:
        """
        Ask the model and return parsed JSON (dict or list).
        Raises the last exception only if all retries fail.
        """
        payload, url, headers = self._build_payload_and_url(system, user)
        last_error: Exception | None = None

        # Attempt up to self.retries times (retries is minimum 1)
        for attempt in range(self.retries):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                body = response.json()

                # Try to extract candidate raw text from known response shapes
                raw_candidate = None
                if isinstance(body, dict):
                    # Ollama /api/generate -> "response"
                    if "response" in body:
                        raw_candidate = body.get("response")
                    # Ollama /api/chat may return {"message": {"content": "..."}}
                    elif "message" in body and isinstance(body.get("message"), dict):
                        raw_candidate = body["message"].get("content", "")
                    # OpenAI-style
                    elif "choices" in body and isinstance(body.get("choices"), list) and body["choices"]:
                        first = body["choices"][0]
                        if isinstance(first, dict):
                            # new style: message.content
                            msg = first.get("message", {})
                            if isinstance(msg, dict):
                                raw_candidate = msg.get("content", "")
                            else:
                                raw_candidate = first.get("text", "")
                else:
                    raw_candidate = body

                # Parse JSON (may raise ValueError)
                parsed = self._parse_json_text(raw_candidate)
                # Log success
                self._log({"chapter_id": chapter_id, "attempt": attempt, "request": payload, "response_raw": raw_candidate, "response_parsed": parsed})
                return parsed

            except Exception as exc:
                last_error = exc
                # Log the failure with raw body if available
                try:
                    body_preview = response.json() if "response" in locals() and response is not None else None
                except Exception:
                    body_preview = None
                self._log({"chapter_id": chapter_id, "attempt": attempt, "request": payload, "response_body": body_preview, "error": str(exc)})
                # small backoff
                time.sleep(0.2 * (attempt + 1))

        # All attempts failed: raise the last exception to let caller decide
        assert last_error is not None
        raise last_error

    def ask_json(self, *, system: str, user: str, chapter_id: str) -> Any:
        return self.ask_json_any(system=system, user=user, chapter_id=chapter_id)


# --- DialogueParser (migrated from models/dialogue_parser.py) ---

@dataclass
class Segment:
    text: str
    speaker: str
    type: str
    gender: str
    speaker_confidence: float = 0.0
    gender_confidence: float = 0.0
    character_confidence: float = 0.0
    paragraph_id: str = ""


@dataclass
class DetectedCharacter:
    name: str
    gender: str = "unknown"
    confidence: float = 0.0


@dataclass
class ParseResult:
    segments: list[Segment]
    detected_characters: list[DetectedCharacter]


class DialogueParser:
    def __init__(
        self,
        *,
        ollama_url: str = "http://127.0.0.1:11434/api/generate",
        model: str | None = None,
        semantic_model: str | None = None,
        fallback_model: str | None = None,
        formatter_model: str | None = None,
        character_db: CharacterDatabase | None = None,
        llm_log_path: str | None = None,
        timeout: int = 300,
        retries: int = 1,
        max_context_tokens: int = 250_000,
    ) -> None:
        # Keep normalization minimal to avoid breaking callers.
        # If user passed an /api/chat or /api/generate endpoint, preserve it.
        self.ollama_url = self._normalize_ollama_url(ollama_url)
        chosen = semantic_model or model or "qwen2.5-coder:7b"
        self.model = chosen
        self.semantic_model = chosen
        self.fallback_model = chosen
        self.formatter_model = chosen
        self.character_db = character_db

        common = dict(
            base_url=self.ollama_url,
            timeout=timeout,
            retries=retries,
            max_context_tokens=max_context_tokens,
            llm_log_path=llm_log_path,
        )

        # Instantiate clients with the same interface as before
        self.client = OllamaChatClient(model=self.semantic_model, **common)
        self.fallback_client = OllamaChatClient(model=self.fallback_model, **common)
        self.formatter_client = OllamaChatClient(model=self.formatter_model, **common)
        self.service = DialogueSegmentationService(client=self.client, fallback_client=self.fallback_client, formatter_client=self.formatter_client)

    @staticmethod
    def _normalize_ollama_url(url: str) -> str:
        """
        Preserve explicit endpoints if provided. If user passed a base host,
        return it unchanged (the client will append /api/chat).
        """
        if not url:
            return "http://127.0.0.1:11434/api/generate"
        url = url.rstrip("/")
        # If user provided /api/chat or /api/generate, keep it
        if url.endswith("/api/chat") or url.endswith("/api/generate"):
            return url
        return url

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = TextCleaner.clean_text(text or "")
        lines = [line for line in cleaned.splitlines() if line.strip().casefold() not in {"next chapter", "subscribe now"}]
        return "\n".join(lines).strip()

    def _known_characters(self) -> list[dict]:
        if not self.character_db:
            return []
        return [asdict(char) for char in self.character_db.all()]

    def _canonicalize_name(self, name: str) -> tuple[str, str | None]:
        cleaned = (name or "").strip()
        while cleaned and cleaned[-1] in ".,!?;:":
            cleaned = cleaned[:-1].rstrip()
        lowered = cleaned.casefold()
        if lowered == "unknown":
            return "unknown", None
        if lowered == "narrator":
            return "narrator", None
        if self.character_db:
            resolved = self.character_db.resolve_name(cleaned)
            if resolved:
                return resolved.name, resolved.gender
        return cleaned or "unknown", None

    def parse(self, text: str, chapter_id: str, manual_segment_hints=None) -> ParseResult:
        cleaned = self._clean_text(text)
        try:
            llm_result = self.service.parse(
                text=cleaned,
                chapter_id=chapter_id,
                known_characters=self._known_characters(),
                manual_segment_hints=manual_segment_hints,
            )
            segments: list[Segment] = []
            for item in llm_result.segments:
                speaker, canonical_gender = self._canonicalize_name(item.speaker)
                segments.append(
                    Segment(
                        text=item.text,
                        speaker=speaker,
                        type=item.type if item.type in {"dialogue", "thought", "narration"} else "narration",
                        gender=canonical_gender or item.gender or "unknown",
                        speaker_confidence=float(item.speaker_confidence or 0.0),
                        gender_confidence=float(item.gender_confidence or 0.0),
                        character_confidence=float(item.character_confidence or 0.0),
                        paragraph_id=item.paragraph_id,
                    )
                )
            if not segments:
                raise ValueError("No segments returned")
            detected: list[DetectedCharacter] = []
            seen = set()
            for item in llm_result.detected_characters:
                name, canonical_gender = self._canonicalize_name(item.name)
                key = name.casefold()
                if not name or key in seen:
                    continue
                seen.add(key)
                detected.append(DetectedCharacter(name=name, gender=canonical_gender or item.gender or "unknown", confidence=float(item.confidence or 0.0)))
            return ParseResult(segments=segments, detected_characters=detected)
        except Exception as exc:
            # Log the exception to the LLM log if available (best-effort)
            try:
                if hasattr(self, "client") and getattr(self.client, "llm_log_path", None):
                    Path(self.client.llm_log_path).parent.mkdir(parents=True, exist_ok=True)
                    with Path(self.client.llm_log_path).open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"chapter_id": chapter_id, "error": str(exc)}, ensure_ascii=False) + "\n")
            except Exception:
                pass
            # Fallback: return a single narrator segment (preserve previous behavior)
            return ParseResult(
                segments=[Segment(text=cleaned or text, speaker="narrator", type="narration", gender="unknown")],
                detected_characters=[],
            )
