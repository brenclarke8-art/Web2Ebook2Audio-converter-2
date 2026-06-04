from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unified prompt template used by the chunked parsing pipeline
# ---------------------------------------------------------------------------

_UNIFIED_PROMPT_TEMPLATE = """\
You MUST output ONLY valid JSON matching the schema below. No prose. No explanations. No extra fields. If unsure, return empty arrays or empty strings.

========================
STRICT JSON SCHEMA
========================
{{
  "characters": [
    {{
      "name": "",
      "gender": ""
    }}
  ],
  "segments": [
    {{
      "type": "",
      "speaker": "",
      "text": ""
    }}
  ]
}}
END_JSON

========================
RULES
========================
- Do NOT invent characters.
- Do NOT merge similar names.
- Do NOT infer relationships not stated.
- If speaker unknown → "Unknown".
- Preserve chronological order.
- Segment types: "dialogue", "thought", "narration".
- Dialogue = spoken lines. Thought = internal monologue. Narration = everything else.
- character gender: "male", "female", or "unknown".
- Do NOT output "actions". Do NOT output "events".
- No trailing commas. No commentary. JSON only.

========================
KNOWN CHARACTERS
========================
{known_characters}

========================
CHAPTER TEXT
========================
{chunk_text}
"""


class OllamaChatClient:
    """Minimal Ollama /api/generate (completion mode) JSON client with structured communication logs."""

    def __init__(
        self,
        *,
        model: str = "mistral:instruct",
        url: str = "http://localhost:11434/api/generate",
        timeout_s: int = 300,
        retries: int = 1,
        max_context_tokens: int = 250_000,
        log_path: Path | str | None = None,
    ) -> None:
        self.model = (model or "mistral:instruct").strip()
        self.url = (url or "http://localhost:11434/api/generate").strip()
        self.timeout_s = int(timeout_s)
        self.retries = max(0, int(retries))
        self.max_context_tokens = max(1, int(max_context_tokens))
        self.disabled = False
        self.log_path = Path(log_path) if log_path else None
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def ask_json(self, *, system: str, user: str | dict[str, Any], chapter_id: str = "ch") -> dict[str, Any]:
        parsed = self.ask_json_any(system=system, user=user, chapter_id=chapter_id)
        return parsed if isinstance(parsed, dict) else {}

    def ask_json_any(self, *, system: str, user: str | dict[str, Any], chapter_id: str = "ch") -> Any:
        if self.disabled:
            return {}

        user_content = user if isinstance(user, str) else json.dumps(user, ensure_ascii=False)
        prompt = f"{system}\n\n{user_content}"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "options": {"temperature": 0, "num_ctx": self.max_context_tokens},
            "stream": False,
        }

        last_error: str | None = None
        for attempt in range(self.retries + 1):
            start = time.perf_counter()
            try:
                response = requests.post(self.url, json=payload, timeout=self.timeout_s)
                response.raise_for_status()
                body = response.json()
                content = body.get("response", "")
                parsed = self._parse_json_content_any(content)
                elapsed = time.perf_counter() - start
                self._write_log_entry(
                    chapter_id=chapter_id,
                    request=payload,
                    response_status=response.status_code,
                    response_raw=content,
                    response_parsed=parsed,
                    elapsed=elapsed,
                )
                return parsed
            except Exception as exc:
                elapsed = time.perf_counter() - start
                last_error = str(exc)
                self._write_log_entry(
                    chapter_id=chapter_id,
                    request=payload,
                    elapsed=elapsed,
                    error=last_error,
                )
                if attempt >= self.retries:
                    logger.warning("Ollama request failed after retries; disabling LLM client: %s", exc)
                    self.disabled = True
                    return {}

        if last_error:
            logger.warning("Ollama request failed: %s", last_error)
        return {}

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any]:
        parsed = OllamaChatClient._parse_json_content_any(content)
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _parse_json_content_any(content: str) -> Any:
        if not content:
            return {}
        raw = content.strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, (dict, list)):
                return parsed
            return {}
        except json.JSONDecodeError:
            pass

        for candidate in OllamaChatClient._json_candidates(raw):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, (dict, list)):
                return parsed
        return {}

    @staticmethod
    def _json_candidates(content: str) -> list[str]:
        candidates = [content]
        for fence in re.findall(r"```(?:json)?\s*(.*?)```", content, re.DOTALL | re.IGNORECASE):
            stripped = fence.strip()
            if stripped:
                candidates.append(stripped)

        candidates.extend(OllamaChatClient._balanced_json_objects(content))

        seen: set[str] = set()
        ordered: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                ordered.append(candidate)
        return ordered

    @staticmethod
    def _balanced_json_objects(content: str) -> list[str]:
        objects: list[str] = []
        start = -1
        depth = 0
        in_string = False
        escape = False

        for idx, ch in enumerate(content):
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == "{":
                if depth == 0:
                    start = idx
                depth += 1
            elif ch == "}":
                if depth == 0:
                    continue
                depth -= 1
                if depth == 0 and start != -1:
                    objects.append(content[start : idx + 1])
                    start = -1
        return objects

    def _write_log_entry(
        self,
        *,
        chapter_id: str,
        request: dict[str, Any],
        response_status: int | None = None,
        response_raw: str | None = None,
        response_parsed: Any | None = None,
        elapsed: float | None = None,
        error: str | None = None,
    ) -> None:
        if not self.log_path:
            return
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "chapter_id": chapter_id,
            "model": self.model,
            "url": self.url,
            "request": request,
        }
        if error is not None:
            record["error"] = error
        else:
            record["response_status"] = response_status
            record["elapsed_seconds"] = None if elapsed is None else round(elapsed, 3)
            record["response_raw"] = response_raw
            record["response_parsed"] = response_parsed or {}
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logger.debug("Failed writing LLM communication log", exc_info=True)

    # -----------------------------------------------------------------------
    # Text compression
    # -----------------------------------------------------------------------

    @staticmethod
    def compress_text(text: str) -> str:
        """Remove noise from *text* to reduce token count before chunking.

        Steps performed (in order):
        1. Strip blank lines.
        2. Collapse multiple spaces / tabs into a single space.
        3. Strip decorative separators (lines consisting only of punctuation /
           repeated characters such as ``---``, ``***``, ``===``).
        4. Trim leading/trailing whitespace from each line and from the whole
           result.
        """
        if not text:
            return ""
        lines = text.splitlines()
        cleaned: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Strip decorative separators: lines made up solely of repeated
            # separator characters (e.g. "---", "===", "***", "###").
            if re.fullmatch(r"[-=*_#~+|]{2,}", stripped):
                continue
            stripped = re.sub(r"[ \t]+", " ", stripped)
            cleaned.append(stripped)
        return "\n".join(cleaned).strip()

    # -----------------------------------------------------------------------
    # Chunking engine
    # -----------------------------------------------------------------------

    def chunk_text(self, text: str, max_chars: int = 6000, overlap: int = 500) -> list[str]:
        """Split *text* into overlapping chunks that each fit within *max_chars*.

        Uses a sliding-window approach so each chunk overlaps the previous one
        by *overlap* characters, preserving narrative continuity at chunk
        boundaries.  Chunk boundaries are aligned to newlines where possible.
        """
        if not text:
            return []
        if len(text) <= max_chars:
            return [text]

        chunks: list[str] = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + max_chars, text_len)

            # Try to align the cut to a newline boundary within the last 10 %
            if end < text_len:
                search_from = max(start, end - max(1, max_chars // 10))
                nl_pos = text.rfind("\n", search_from, end)
                if nl_pos > start:
                    end = nl_pos + 1

            chunks.append(text[start:end])

            if end >= text_len:
                break

            # Advance start by (max_chars - overlap), aligned to newline
            next_start = end - overlap
            if next_start <= start:
                next_start = start + 1  # always make progress
            nl_pos = text.find("\n", next_start, end)
            if nl_pos != -1:
                next_start = nl_pos + 1
            start = next_start

        return chunks

    # -----------------------------------------------------------------------
    # Unified prompt builder
    # -----------------------------------------------------------------------

    def build_unified_prompt(self, chunk_text: str, character_memory: Any) -> str:
        """Return the production-ready unified prompt string.

        *character_memory* may be ``None``, a list of dicts with ``name`` /
        ``gender`` / ``role`` keys, a list of strings, or any object with an
        ``all()`` method (``CharacterDB``).
        """
        lines: list[str] = []

        if character_memory is None:
            pass
        elif hasattr(character_memory, "all"):
            for char in character_memory.all():
                name = getattr(char, "name", "")
                gender = getattr(char, "gender", "unknown")
                if name:
                    parts = [f"- {name}"]
                    if gender and gender != "unknown":
                        parts.append(f"gender={gender}")
                    lines.append(" | ".join(parts))
        elif isinstance(character_memory, list):
            for item in character_memory:
                if isinstance(item, str):
                    if item.strip():
                        lines.append(f"- {item.strip()}")
                elif isinstance(item, dict):
                    name = str(item.get("name", "")).strip()
                    if not name:
                        continue
                    gender = str(item.get("gender", "unknown")).strip().lower()
                    parts = [f"- {name}"]
                    if gender and gender != "unknown":
                        parts.append(f"gender={gender}")
                    lines.append(" | ".join(parts))

        known_characters_block = "\n".join(lines) if lines else "(none known yet)"
        return _UNIFIED_PROMPT_TEMPLATE.format(
            known_characters=known_characters_block,
            chunk_text=chunk_text,
        )

    # -----------------------------------------------------------------------
    # Completion-mode LLM call
    # -----------------------------------------------------------------------

    def call_unified_prompt(self, prompt: str, chapter_id: str = "chunk") -> str:
        """Send *prompt* to Ollama /api/generate and return the raw response text.

        Uses ``stream=False`` and ``temperature=0`` for determinism.
        Returns an empty string on failure.  Writes to the communication log
        when :attr:`log_path` is set.
        """
        if self.disabled:
            return ""

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "options": {"temperature": 0, "num_ctx": self.max_context_tokens},
            "stream": False,
        }

        for attempt in range(self.retries + 1):
            start = time.perf_counter()
            try:
                response = requests.post(self.url, json=payload, timeout=self.timeout_s)
                response.raise_for_status()
                body = response.json()
                raw_text = body.get("response", "")
                elapsed = time.perf_counter() - start
                parsed = self._parse_json_content(raw_text)
                self._write_log_entry(
                    chapter_id=chapter_id,
                    request=payload,
                    response_status=response.status_code,
                    response_raw=raw_text,
                    response_parsed=parsed,
                    elapsed=elapsed,
                )
                return raw_text
            except Exception as exc:
                elapsed = time.perf_counter() - start
                last_error = str(exc)
                self._write_log_entry(
                    chapter_id=chapter_id,
                    request=payload,
                    elapsed=elapsed,
                    error=last_error,
                )
                logger.warning(
                    "call_unified_prompt attempt %d/%d failed (%.1fs): %s",
                    attempt + 1,
                    self.retries + 1,
                    elapsed,
                    exc,
                )
                if attempt >= self.retries:
                    self.disabled = True
                    return ""
        return ""

    # -----------------------------------------------------------------------
    # Chunk parser
    # -----------------------------------------------------------------------

    def parse_chunk(self, chunk_text: str, chapter_id: str, memory: Any = None) -> dict[str, Any]:
        """Parse a single *chunk_text* using the unified prompt.

        Builds the prompt, calls the LLM, JSON-parses the response, and
        returns the parsed dict (empty dict on failure).
        """
        prompt = self.build_unified_prompt(chunk_text, memory)
        raw_text = self.call_unified_prompt(prompt, chapter_id=chapter_id)
        if not raw_text:
            return {}
        return self._parse_json_content(raw_text)

    # -----------------------------------------------------------------------
    # Chunk merger
    # -----------------------------------------------------------------------

    @staticmethod
    def merge_semantic_chunks(results: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge a list of per-chunk parse results into a single unified result.

        Merging rules:
        - **characters**: deduplicated by name (case-insensitive); first occurrence wins
          for ``gender``.
        - **segments**: appended in order with overlap deduplication — segments whose
          normalised text was already seen within the previous
          ``_CHUNK_DEDUP_WINDOW`` entries are silently dropped.
        """
        _CHUNK_DEDUP_WINDOW = 15

        merged_chars: dict[str, dict[str, Any]] = {}
        merged_segments: list[dict[str, Any]] = []
        recent_texts: deque[str] = deque(maxlen=_CHUNK_DEDUP_WINDOW)

        for result in results:
            if not isinstance(result, dict):
                continue

            for char in result.get("characters", []):
                if not isinstance(char, dict):
                    continue
                name = str(char.get("name", "")).strip()
                if not name:
                    continue
                key = name.lower()
                if key not in merged_chars:
                    merged_chars[key] = {
                        "name": name,
                        "gender": str(char.get("gender", "unknown")).strip().lower() or "unknown",
                    }

            for seg in result.get("segments", []):
                if not isinstance(seg, dict):
                    continue
                text = str(seg.get("text", "")).strip()
                if not text:
                    continue
                # Normalise whitespace for dedup comparison only
                norm = " ".join(text.split())
                if norm in recent_texts:
                    continue
                merged_segments.append(seg)
                recent_texts.append(norm)

        return {
            "characters": list(merged_chars.values()),
            "segments": merged_segments,
        }

    # -----------------------------------------------------------------------
    # Main chunked parser
    # -----------------------------------------------------------------------

    def parse_chapter_chunked(
        self,
        text: str,
        chapter_id: str,
        memory: Any = None,
        max_chars: int = 6000,
        overlap: int = 500,
    ) -> dict[str, Any]:
        """Parse a long chapter by splitting it into overlapping chunks.

        Steps:
        1. Compress text (remove blank lines, collapse spaces, strip decorators).
        2. Split into overlapping chunks.
        3. Parse each chunk individually via :meth:`parse_chunk`.
        4. Merge all chunk results into a single unified dict.
        5. Return the merged dict.
        """
        compressed = self.compress_text(text)
        chunks = self.chunk_text(compressed, max_chars=max_chars, overlap=overlap)
        logger.debug(
            "parse_chapter_chunked: chapter=%s compressed=%d chars split into %d chunk(s)",
            chapter_id,
            len(compressed),
            len(chunks),
        )

        results: list[dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{chapter_id}_chunk{i}"
            parsed = self.parse_chunk(chunk, chunk_id, memory)
            if parsed:
                results.append(parsed)

        if not results:
            return {}

        return self.merge_semantic_chunks(results)

    # -----------------------------------------------------------------------
    # Single-call chapter parser (unified prompt, no chunking)
    # -----------------------------------------------------------------------

    def parse_chapter(
        self,
        text: str,
        chapter_id: str,
        memory: Any = None,
    ) -> dict[str, Any]:
        """Parse a chapter in a single LLM call using the unified prompt.

        Suitable for chapters that fit within the model's context window
        (≤ 6 000 characters after compression).
        """
        compressed = self.compress_text(text)
        return self.parse_chunk(compressed, chapter_id, memory)
