from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests


@dataclass
class LLMClient:
    """
    Backwards-compatible LLM client used by the repo.

    - Keeps the same public API (generate_json, classify).
    - Adds robust Ollama support (format: "json") for local provider.
    - Adds tolerant JSON extraction.
    - Adds optional per-chapter JSONL logging via llm_log_path.
    - Keeps original return semantics: returns {} on failure.
    - Performs a safe 404 -> /api/chat fallback when appropriate.
    """

    base_url: str
    model: str
    timeout: int = 120
    retries: int = 1
    provider: str = "ollama_local"
    api_key: str = ""
    llm_log_path: str | None = None
    max_context_tokens: int = 8192

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    def generate_json(self, *, system: str, user: str) -> Dict[str, Any] | List[Dict[str, Any]]:
        payload, headers, url = self._build_request(system=system, user=user)
        last_error = None
        attempted_chat_fallback = False

        for attempt in range(self.retries + 1):
            resp = None
            try:
                # Build kwargs compatible with test fakes (which reject headers)
                post_kwargs = {"json": payload, "timeout": self.timeout}
                try:
                    if headers:
                        resp = requests.post(url, headers=headers, **post_kwargs)
                    else:
                        resp = requests.post(url, **post_kwargs)
                except TypeError:
                    # test fake doesn't accept headers → retry without them
                    resp = requests.post(url, **post_kwargs)

                # 404 fallback: /api/generate → /api/chat
                if resp.status_code == 404 and url.endswith("/api/generate") and not attempted_chat_fallback:
                    attempted_chat_fallback = True
                    chat_url = url[:-len("/api/generate")] + "/api/chat"

                    # Convert generate payload → chat payload if needed
                    if "messages" not in payload and "prompt" in payload:
                        messages = [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ]
                        payload = {
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            "format": "json",
                            "options": {
                                "temperature": 0.0,
                                "num_ctx": min(self.max_context_tokens, 8192),
                            },
                        }

                    url = chat_url
                    time.sleep(0.1)
                    continue

                resp.raise_for_status()
                parsed = self._parse_response(resp.json())
                self._log({"attempt": attempt, "parsed": parsed})
                return parsed

            except Exception as exc:
                last_error = exc
                try:
                    body_text = resp.text if resp is not None else None
                except Exception:
                    body_text = None
                self._log({"attempt": attempt, "error": str(exc), "body": body_text})
                time.sleep(0.2 * (attempt + 1))

        return {}

    def classify(self, prompt: str) -> Dict[str, Any]:
        result = self.generate_json(system="Return JSON only.", user=prompt)
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Request builder
    # -------------------------------------------------------------------------
    def _build_request(self, *, system: str, user: str) -> Tuple[Dict[str, Any], Dict[str, str], str]:
        provider = (self.provider or "ollama_local").strip().lower()
        base = self.base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}

        # External cloud (OpenAI-style)
        if provider in {"external_cloud", "openai", "openai_cloud"}:
            if self.api_key:
                headers["Authorization"] = "Bearer " + self.api_key
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
            }
            return payload, headers, base

        # Ollama /api/chat
        if base.endswith("/api/chat"):
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.0,
                    "num_ctx": min(self.max_context_tokens, 8192),
                },
            }
            return payload, headers, base

        # Ollama /api/generate
        if base.endswith("/api/generate"):
            prompt = f"{system.strip()}\n\n{user.strip()}\n\nRespond ONLY with valid JSON."
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.0,
                    "num_ctx": min(self.max_context_tokens, 8192),
                },
            }
            return payload, headers, base

        # Bare host → default to /api/chat
        if base.endswith(":11434") or base.endswith("11434"):
            url = base + "/api/chat"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.0,
                    "num_ctx": min(self.max_context_tokens, 8192),
                },
            }
            return payload, headers, url

        # Fallback: treat as generate endpoint
        url = base
        prompt = f"{system.strip()}\n\n{user.strip()}\n\nRespond ONLY with valid JSON."
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,
                "num_ctx": min(self.max_context_tokens, 8192),
            },
        }
        return payload, headers, url

    # -------------------------------------------------------------------------
    # Response parsing
    # -------------------------------------------------------------------------
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

    def _parse_response(self, data: Any) -> Dict[str, Any] | List[Dict[str, Any]]:
        try:
            if isinstance(data, dict) and "response" in data:
                return self._parse_json_text(data["response"])

            if isinstance(data, dict) and "message" in data:
                return self._parse_json_text(data["message"].get("content", ""))

            if isinstance(data, dict) and "choices" in data:
                first = data["choices"][0]
                content = (
                    first.get("message", {}).get("content", "")
                    or first.get("text", "")
                    or first.get("delta", {}).get("content", "")
                )
                return self._parse_json_text(content)

            if isinstance(data, (dict, list)):
                return data

        except Exception:
            pass

        return {}

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    def _log(self, record: Dict[str, Any]) -> None:
        if not self.llm_log_path:
            return
        try:
            p = Path(self.llm_log_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass


# -------------------------------------------------------------------------
# Compatibility shim for older code that expects OllamaChatClient
# -------------------------------------------------------------------------
class OllamaChatClient:
    """
    Backwards-compatible shim that preserves the old OllamaChatClient constructor
    and method names (ask_json_any, ask_json). Internally delegates to LLMClient.
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

        self._client = LLMClient(
            base_url=base_url,
            model=model,
            timeout=timeout,
            retries=retries,
            provider="ollama_local",
            api_key="",
            llm_log_path=llm_log_path,
            max_context_tokens=min(int(max_context_tokens), 8192),
        )

        self.llm_log_path = llm_log_path

    def ask_json_any(self, *, system: str, user: str, chapter_id: str) -> Any:
        try:
            return self._client.generate_json(system=system, user=user)
        except Exception:
            raise

    def ask_json(self, *, system: str, user: str, chapter_id: str) -> Any:
        return self.ask_json_any(system=system, user=user, chapter_id=chapter_id)
