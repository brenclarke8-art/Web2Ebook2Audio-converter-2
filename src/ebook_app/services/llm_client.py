from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

_JSON_REPAIR_SYSTEM_PROMPT = (
    "You are a JSON repair engine.\n"
    "Fix the JSON so it is valid and parseable.\n"
    "Do NOT add commentary.\n"
    "Return ONLY valid JSON."
)


class OllamaChatClient:
    """Minimal Ollama /api/chat JSON client with structured communication logs."""

    def __init__(
        self,
        *,
        model: str = "mistral:instruct",
        url: str = "http://localhost:11434/api/chat",
        timeout_s: int = 300,
        retries: int = 1,
        max_context_tokens: int = 250_000,
        log_path: Path | str | None = None,
    ) -> None:
        self.model = (model or "mistral:instruct").strip()
        self.url = (url or "http://localhost:11434/api/chat").strip()
        self.timeout_s = int(timeout_s)
        self.retries = max(0, int(retries))
        self.max_context_tokens = max(1, int(max_context_tokens))
        self.disabled = False
        self.log_path = Path(log_path) if log_path else None
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def ask_json(self, *, system: str, user: str | dict[str, Any], chapter_id: str = "ch") -> dict[str, Any]:
        if self.disabled:
            return {}

        user_content = user if isinstance(user, str) else json.dumps(user, ensure_ascii=False)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
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
                content = body.get("message", {}).get("content", "")
                parsed = self._parse_json_content(content)
                if not parsed and content:
                    parsed = self._repair_json_content(content)
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
        if not content:
            return {}
        raw = content.strip()
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass

        for candidate in OllamaChatClient._json_candidates(raw):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
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

    def _repair_json_content(self, content: str) -> dict[str, Any]:
        repair_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _JSON_REPAIR_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "options": {"num_ctx": self.max_context_tokens},
            "stream": False,
        }
        try:
            response = requests.post(self.url, json=repair_payload, timeout=self.timeout_s)
            response.raise_for_status()
            repaired = response.json().get("message", {}).get("content", "")
            return self._parse_json_content(repaired)
        except Exception:
            logger.debug("LLM JSON repair failed", exc_info=True)
            return {}

    def _write_log_entry(
        self,
        *,
        chapter_id: str,
        request: dict[str, Any],
        response_status: int | None = None,
        response_raw: str | None = None,
        response_parsed: dict[str, Any] | None = None,
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
