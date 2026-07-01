from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

from ebook_app.app.state.character_db import CharacterDatabase
from ebook_app.text.parse.html_cleaner import TextCleaner
from ebook_app.text.segment.segmenter import DialogueSegmentationService

logger = logging.getLogger(__name__)


class OllamaChatClient:
    """
    Lightweight, tolerant Ollama client wrapper.

    - Supports both /api/chat and /api/generate endpoints with 404 fallback.
    - Forces JSON output when possible (format: "json").
    - Robust JSON extraction from fenced or noisy responses.
    - Per-chapter JSONL logging when llm_log_path is provided.
    - Retries with small backoff; surfaces errors to caller on final failure.
    - Honors max_context_tokens without hard-capping at 8192.
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
            pass

    # -------------------------
    # JSON extraction helpers
    # -------------------------
    @staticmethod
    def _parse_json_text(raw: Any) -> Any:
        if isinstance(raw, (dict, list)):
            return raw

        text = "" if raw is None else str(raw).strip()

        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except Exception:
            pass

        obj_start = text.find("{")
        arr_start = text.find("[")
        starts = [i for i in (obj_start, arr_start) if i != -1]
        if starts:
            start = min(starts)
            last_obj = text.rfind("}")
            last_arr = text.rfind("]")
            end = last_obj if last_obj > last_arr else last_arr
            if end > start:
                snippet = text[start : end + 1]
                try:
                    return json.loads(snippet)
                except Exception:
                    pass

        raise ValueError("Unable to parse JSON from LLM response")

    def _chat_payload(self, system: str, user: str) -> dict:
        """Build a /api/chat-style payload."""
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_ctx": self.max_context_tokens},
        }

    # -------------------------
    # Internal payload builder
    # -------------------------
    def _build_payload_and_url(self, system: str, user: str):
        url = self.base_url
        headers = {"Content-Type": "application/json"}

        if url.endswith("/api/chat"):
            return self._chat_payload(system, user), url, headers

        if url.endswith("/api/generate"):
            prompt = f"{system.strip()}\n\n{user.strip()}\n\nRespond ONLY with valid JSON."
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0, "num_ctx": self.max_context_tokens},
            }
            return payload, url, headers

        if url.endswith(":11434") or url.endswith("11434"):
            return self._chat_payload(system, user), url + "/api/chat", headers

        prompt = f"{system.strip()}\n\n{user.strip()}\n\nRespond ONLY with valid JSON."
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_ctx": self.max_context_tokens},
        }
        return payload, url, headers

    # -------------------------
    # Public ask methods
    # -------------------------
    def ask_json_any(self, *, system: str, user: str, chapter_id: str) -> Any:
        payload, url, headers = self._build_payload_and_url(system, user)
        last_error = None
        attempted_chat_fallback = False

        for attempt in range(self.retries + 1):
            response = None
            try:
                logger.debug("LLM request chapter=%s attempt=%s url=%s payload=%s", chapter_id, attempt, url, payload)
                post_kwargs = {"json": payload, "timeout": self.timeout}
                try:
                    if headers:
                        response = requests.post(url, headers=headers, **post_kwargs)
                    else:
                        response = requests.post(url, **post_kwargs)
                except TypeError:
                    response = requests.post(url, **post_kwargs)

                # 404 fallback: /api/generate → /api/chat (counts as an attempt)
                if (
                    response.status_code == 404
                    and url.endswith("/api/generate")
                    and not attempted_chat_fallback
                ):
                    attempted_chat_fallback = True
                    url = url[: -len("/api/generate")] + "/api/chat"
                    payload = self._chat_payload(system, user)
                    time.sleep(0.1)
                    continue

                response.raise_for_status()
                body = response.json()
                response_body = getattr(response, "text", None)
                logger.debug(
                    "LLM response chapter=%s attempt=%s status=%s body=%s",
                    chapter_id,
                    attempt,
                    getattr(response, "status_code", None),
                    response_body,
                )

                if isinstance(body, dict):
                    if "response" in body:
                        raw_candidate = body["response"]
                    elif "message" in body:
                        raw_candidate = body["message"].get("content", "")
                    elif "choices" in body:
                        first = body["choices"][0]
                        raw_candidate = first.get("message", {}).get("content", "") or first.get("text", "")
                    else:
                        raw_candidate = body
                else:
                    raw_candidate = body

                parsed = self._parse_json_text(raw_candidate)
                logger.debug("LLM parsed response chapter=%s attempt=%s parsed=%s", chapter_id, attempt, parsed)
                self._log({
                    "chapter_id": chapter_id,
                    "attempt": attempt,
                    "url": url,
                    "model": self.model,
                    "status_code": getattr(response, "status_code", None),
                    "request": payload,
                    "response_body": response_body,
                    "response_raw": raw_candidate,
                    "parsed": parsed,
                })
                return parsed

            except Exception as exc:
                last_error = exc
                response_body = None
                if response is not None:
                    response_body = getattr(response, "text", None)
                logger.debug(
                    "LLM request failed chapter=%s attempt=%s url=%s error=%s",
                    chapter_id,
                    attempt,
                    url,
                    exc,
                    exc_info=True,
                )
                self._log({
                    "chapter_id": chapter_id,
                    "attempt": attempt,
                    "url": url,
                    "model": self.model,
                    "request": payload,
                    "response_body": response_body,
                    "error": str(exc),
                })
                time.sleep(0.2 * (attempt + 1))

        raise last_error

    def ask_json(self, *, system: str, user: str, chapter_id: str) -> Any:
        return self.ask_json_any(system=system, user=user, chapter_id=chapter_id)


# --- DialogueParser ----------------------------------------------------------

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

        self.client = OllamaChatClient(model=self.semantic_model, **common)
        self.fallback_client = OllamaChatClient(model=self.fallback_model, **common)
        self.formatter_client = OllamaChatClient(model=self.formatter_model, **common)
        self.service = DialogueSegmentationService(
            client=self.client,
            fallback_client=self.fallback_client,
            formatter_client=self.formatter_client,
        )

    @staticmethod
    def _normalize_ollama_url(url: str) -> str:
        """
        Normalize the Ollama URL.

        - Both /api/chat and /api/generate are accepted as-is (LLMClient handles both).
        - Bare host (no path) gets /api/generate appended for backward compatibility.
        - Any other URL is kept unchanged.
        """
        if not url:
            return "http://127.0.0.1:11434/api/generate"

        url = url.rstrip("/")

        # Already an explicit endpoint — keep as-is
        if url.endswith("/api/generate") or url.endswith("/api/chat"):
            return url

        # Bare ":11434" host — append default path
        if url.endswith(":11434") or (
            (url.startswith("http://") or url.startswith("https://"))
            and "/" not in url.split("://", 1)[-1]
        ):
            return url + "/api/generate"

        # Custom endpoint — keep unchanged
        return url

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = TextCleaner.clean_text(text or "")
        lines = [
            line
            for line in cleaned.splitlines()
            if line.strip().casefold() not in {"next chapter", "subscribe now"}
        ]
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
                detected.append(
                    DetectedCharacter(
                        name=name,
                        gender=canonical_gender or item.gender or "unknown",
                        confidence=float(item.confidence or 0.0),
                    )
                )
            return ParseResult(segments=segments, detected_characters=detected)
        except Exception as exc:
            logger.warning(
                "DialogueParser.parse: LLM call failed for chapter %r — falling back to narrator. Error: %s",
                chapter_id,
                exc,
            )
            try:
                if hasattr(self, "client") and getattr(self.client, "llm_log_path", None):
                    Path(self.client.llm_log_path).parent.mkdir(parents=True, exist_ok=True)
                    with Path(self.client.llm_log_path).open("a", encoding="utf-8") as fh:
                        fh.write(
                            json.dumps({"chapter_id": chapter_id, "error": str(exc)}, ensure_ascii=False)
                            + "\n"
                        )
            except Exception:
                pass
            return ParseResult(
                segments=[Segment(text=cleaned or text, speaker="narrator", type="narration", gender="unknown")],
                detected_characters=[],
            )
