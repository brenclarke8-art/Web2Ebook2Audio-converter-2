# ebook_app/text/identify/type_classifier.py
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema constants for batch classification output validation
# ---------------------------------------------------------------------------
_REQUIRED_KEYS: frozenset[str] = frozenset(
    {"id", "type", "speaker", "gender", "speaker_confidence", "gender_confidence", "character_confidence"}
)
_VALID_TYPES: frozenset[str] = frozenset({"dialogue", "thought", "narration"})
_CONFIDENCE_KEYS: tuple[str, ...] = ("speaker_confidence", "gender_confidence", "character_confidence")


@dataclass
class LLMClient:
    """
    Backwards-compatible LLM client used by the repo.

    - Keeps the same public API (generate_json, classify).
    - Adds robust Ollama support (format: "json") for local provider.
    - Adds tolerant JSON extraction.
    - Adds optional per-chapter JSONL logging via llm_log_path.
    - Keeps original return semantics: returns {} on failure.
    - Adds optional on_conversation callback for real-time monitoring.
    """

    base_url: str
    model: str
    timeout: int = 120
    retries: int = 1
    provider: str = "ollama_local"
    api_key: str = ""
    # Optional: path to write per-chapter JSONL logs (best-effort)
    llm_log_path: str | None = None
    # Optional: limit context tokens used in options (best-effort)
    max_context_tokens: int = 8192
    # Optional: callback(role, content) called before each request and after each response.
    # role is 'request' (before sending) or 'response' (after receiving).
    on_conversation: Optional[Callable[[str, str], None]] = field(default=None, compare=False)

    # -------------------------
    # Public API
    # -------------------------
    def generate_json(self, *, system: str, user: str) -> Dict[str, Any] | List[Dict[str, Any]]:
        """
        Send a request to the configured provider and return parsed JSON (dict or list).
        On failure, returns {} (keeps original behavior).
        """
        payload, headers, url = self._build_request(system=system, user=user)
        last_error = None

        # Notify conversation monitor before sending
        if callable(self.on_conversation):
            try:
                self.on_conversation("request", user)
            except Exception:
                pass

        for attempt in range(self.retries + 1):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                parsed = self._parse_response(resp.json())
                # Log success (best-effort)
                self._log({"attempt": attempt, "request": payload, "response_raw": resp.text, "response_parsed": parsed})
                # Notify conversation monitor after receiving response
                if callable(self.on_conversation):
                    try:
                        self.on_conversation("response", resp.text)
                    except Exception:
                        pass
                return parsed
            except Exception as exc:
                last_error = exc
                # Log failure (best-effort)
                try:
                    body_text = resp.text if "resp" in locals() and resp is not None else None
                except Exception:
                    body_text = None
                self._log({"attempt": attempt, "request": payload, "response_body": body_text, "error": str(exc)})
                # small backoff
                time.sleep(0.2 * (attempt + 1))
                # continue to next attempt

        # All attempts failed: return empty dict to preserve previous behavior
        return {}

    def classify(self, prompt: str) -> Dict[str, Any]:
        result = self.generate_json(system="Return JSON only.", user=prompt)
        return result if isinstance(result, dict) else {}

    # -------------------------
    # Request builder
    # -------------------------
    def _build_request(self, *, system: str, user: str) -> Tuple[Dict[str, Any], Dict[str, str], str]:
        """
        Build payload, headers, and final URL depending on provider.
        Returns (payload, headers, url).
        """
        provider = (self.provider or "ollama_local").strip().lower()

        # External cloud (OpenAI-style)
        if provider in {"external_cloud", "openai", "openai_cloud"}:
            headers: Dict[str, str] = {"Content-Type": "application/json"}
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
            url = self.base_url.rstrip("/")
            return payload, headers, url

        # Ollama local (preferred)
        # Accept either a full endpoint or a host. If base_url contains /api/chat or /api/generate, use it.
        base = self.base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}

        # If user provided a full endpoint
        if base.endswith("/api/chat"):
            url = base
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0, "num_ctx": min(int(self.max_context_tokens), 8192)},
            }
            return payload, headers, url

        if base.endswith("/api/generate"):
            url = base
            prompt = f"{system.strip()}\n\n{user.strip()}\n\nRespond ONLY with valid JSON. No commentary, no markdown."
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0, "num_ctx": min(int(self.max_context_tokens), 8192)},
            }
            return payload, headers, url

        # If base looks like a host (e.g., http://127.0.0.1:11434) prefer /api/chat
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
                "options": {"temperature": 0.0, "num_ctx": min(int(self.max_context_tokens), 8192)},
            }
            return payload, headers, url

        # Fallback: assume generate-like endpoint at provided url
        url = base
        prompt = f"{system.strip()}\n\n{user.strip()}\n\nRespond ONLY with valid JSON. No commentary, no markdown."
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_ctx": min(int(self.max_context_tokens), 8192)},
        }
        return payload, headers, url

    # -------------------------
    # Response parsing
    # -------------------------
    @staticmethod
    def _parse_json_text(raw: Any) -> Any:
        """
        Tolerant JSON extraction:
        - If raw is already dict/list, return it.
        - Strip fenced code blocks.
        - Try json.loads on the whole text.
        - Try to extract the first {...} or [...] substring.
        - On failure, raise ValueError.
        """
        if isinstance(raw, (dict, list)):
            return raw

        text = "" if raw is None else str(raw).strip()

        # Strip fenced code blocks (``` or ```json)
        if text.startswith("```"):
            lines = text.splitlines()
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
        starts = [i for i in (obj_start, arr_start) if i != -1]
        if starts:
            start = min(starts)
            # naive end detection: last } or ]
            last_obj = text.rfind("}")
            last_arr = text.rfind("]")
            if last_obj != -1 and last_obj > last_arr:
                end = last_obj
            else:
                end = last_arr
            if start != -1 and end != -1 and end > start:
                snippet = text[start : end + 1]
                try:
                    return json.loads(snippet)
                except Exception:
                    pass

        raise ValueError("Unable to parse JSON from LLM response")

    def _parse_response(self, data: Any) -> Dict[str, Any] | List[Dict[str, Any]]:
        """
        Normalize common response shapes:
        - Ollama /api/generate -> {"response": "..."}
        - Ollama /api/chat -> {"message": {"content": "..."}}
        - OpenAI-style -> {"choices": [{"message": {"content": "..."}}]}
        - If data is already dict/list, return it.
        - On parse failure, return {}.
        """
        try:
            # Ollama /api/generate
            if isinstance(data, dict) and "response" in data:
                return self._parse_json_text(data.get("response"))

            # Ollama /api/chat style
            if isinstance(data, dict) and "message" in data and isinstance(data.get("message"), dict):
                return self._parse_json_text(data["message"].get("content", ""))

            # OpenAI-style
            if isinstance(data, dict) and "choices" in data:
                choices = data.get("choices", [])
                if choices and isinstance(choices[0], dict):
                    # new style: message.content
                    content = choices[0].get("message", {}).get("content", "")
                    if not content:
                        # fallback to text or delta
                        content = choices[0].get("text", "") or choices[0].get("delta", {}).get("content", "")
                    return self._parse_json_text(content)

            # Already JSON
            if isinstance(data, (dict, list)):
                return data

        except Exception:
            # fall through to return {}
            pass

        return {}

    # -------------------------
    # Logging (best-effort)
    # -------------------------
    def _log(self, record: Dict[str, Any]) -> None:
        if not self.llm_log_path:
            return
        try:
            p = Path(self.llm_log_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            # Never raise from logging
            pass


# -------------------------
# Pass2Classifier (same public API, improved resilience)
# -------------------------
class Pass2Classifier:
    #: Default segments per LLM call.  25–40 improves compliance without
    #: exceeding typical context limits.
    DEFAULT_BATCH_SIZE: int = 30
    #: Maximum per-batch validation retries (0 = initial attempt only).
    MAX_BATCH_RETRIES: int = 2

    def __init__(self, llm_client: LLMClient, batch_size: int = 30) -> None:
        self.llm_client = llm_client
        self.batch_size = max(1, int(batch_size))

    def classify_segment(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        return self.classify_segments([segment])[0]

    def classify_segments(
        self,
        segments: List[Dict[str, Any]],
        chapter_id: str = "",
        should_cancel=None,
        on_conversation: Optional[Callable[[str, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        if not segments:
            return []

        # Temporarily attach conversation callback to LLM client
        _prev_cb = self.llm_client.on_conversation
        if on_conversation is not None:
            self.llm_client.on_conversation = on_conversation

        try:
            output: List[Dict[str, Any]] = []
            for start in range(0, len(segments), self.batch_size):
                if callable(should_cancel) and should_cancel():
                    break
                batch = segments[start : start + self.batch_size]
                output.extend(self._classify_batch(batch=batch, chapter_id=chapter_id, offset=start))
            return output
        finally:
            self.llm_client.on_conversation = _prev_cb

    def assist_pass1_segments(self, segments: List[Dict[str, Any]], chapter_id: str = "") -> List[Dict[str, Any]]:
        assisted: List[Dict[str, Any]] = []
        classified = self.classify_segments(segments, chapter_id=chapter_id)
        for original, predicted in zip(segments, classified):
            out = dict(original)
            predicted_type = str(predicted.get("type", "narration")).strip().lower()
            out["llm_assist_type"] = predicted_type
            out["is_dialogue_candidate"] = bool(out.get("is_dialogue_candidate")) or predicted_type in {"dialogue", "thought"}
            assisted.append(out)
        return assisted

    def _classify_batch(self, *, batch: List[Dict[str, Any]], chapter_id: str, offset: int) -> List[Dict[str, Any]]:
        """
        Classify a batch with a contract-driven prompt and deterministic retry ladder.

        Attempt 0: base prompt with explicit cardinality and id list.
        Attempt 1: corrective suffix referencing the validation error.
        Attempt 2: compact strict prompt.

        If all attempts fail validation the batch falls back to deterministic defaults.
        """
        entries: List[Dict[str, Any]] = []
        for idx, segment in enumerate(batch):
            entry_id = f"{chapter_id or 'segment'}_{offset + idx}"
            entries.append(
                {
                    "id": entry_id,
                    "text": str(segment.get("text", "")),
                    "prior_segment_text": str(segment.get("context_before", "")),
                    "next_segment_text": str(segment.get("context_after", "")),
                    "is_dialogue_candidate": bool(segment.get("is_dialogue_candidate", False)),
                }
            )

        expected_ids: List[str] = [e["id"] for e in entries]
        n = len(entries)
        id_list_str = ", ".join(expected_ids)
        user = json.dumps(entries, ensure_ascii=False)

        def _base_system() -> str:
            return (
                "You are a semantic classifier for novel text segments. "
                f"Return ONLY a JSON array of exactly {n} objects — one object per input id. "
                "Do not output any prose, markdown, or wrapper object. "
                "Your response MUST start with '[' and end with ']'. "
                "Each object must have ONLY these keys: "
                "id, type, speaker, gender, speaker_confidence, gender_confidence, character_confidence. "
                "Allowed type values: dialogue, thought, narration. "
                "Confidence values must be numbers in [0.0, 1.0]. "
                f"Input ids to process (in order): {id_list_str}"
            )

        def _retry1_system(error: str) -> str:
            return (
                _base_system()
                + f"\n\nIMPORTANT: Your previous response was invalid. Error: {error}. "
                f"Return exactly {n} objects, one for each id in: {id_list_str}."
            )

        def _retry2_system() -> str:
            return (
                f"Return ONLY a JSON array of {n} objects. "
                f"Ids: {id_list_str}. "
                "Keys per object: id,type,speaker,gender,"
                "speaker_confidence,gender_confidence,character_confidence. "
                "type in [dialogue,thought,narration]. Confidence 0.0-1.0. "
                "No text outside the JSON array."
            )

        last_error: Optional[str] = None
        model_name = getattr(self.llm_client, "model", "unknown")

        for attempt in range(self.MAX_BATCH_RETRIES + 1):
            if attempt == 0:
                system = _base_system()
            elif attempt == 1:
                system = _retry1_system(last_error or "unknown error")
            else:
                system = _retry2_system()

            t0 = time.monotonic()
            raw = self.llm_client.generate_json(system=system, user=user)
            latency = time.monotonic() - t0

            validated, error = self._validate_batch_response(raw, expected_ids)

            logger.info(
                "classify_batch chapter=%s batch_offset=%d batch_size=%d "
                "attempt=%d model=%s valid=%s error=%r latency_s=%.2f",
                chapter_id,
                offset,
                n,
                attempt,
                model_name,
                error is None,
                error,
                latency,
            )

            if error is None:
                by_id: Dict[str, Dict[str, Any]] = {
                    str(item["id"]).strip(): item for item in validated
                }
                return [
                    self._build_required_segment(segment=seg, classified=by_id.get(entries[idx]["id"]))
                    for idx, seg in enumerate(batch)
                ]

            last_error = error
            if attempt < self.MAX_BATCH_RETRIES:
                time.sleep(0.1 * (attempt + 1))

        logger.warning(
            "classify_batch chapter=%s offset=%d: all %d attempts failed; "
            "falling back to defaults. last_error=%r",
            chapter_id,
            offset,
            self.MAX_BATCH_RETRIES + 1,
            last_error,
        )
        return [self._build_required_segment(segment=seg, classified=None) for seg in batch]

    @staticmethod
    def _validate_batch_response(
        raw: Any, expected_ids: List[str]
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Validate a batch LLM response against the classification output contract.

        Returns ``(items, None)`` on success or ``([], error_message)`` on failure.
        Contract:
        - top-level must be a JSON array
        - every item must be a dict with exactly the required keys
        - ``type`` must be one of ``dialogue | thought | narration``
        - each confidence field must be a float in ``[0.0, 1.0]``
        - the set of returned ``id`` values must exactly match ``expected_ids``
          (no missing, no duplicates, no extras)
        """
        if not isinstance(raw, list):
            return [], f"Top-level must be an array, got {type(raw).__name__}"

        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                return [], f"Item {i} is not an object"
            missing = _REQUIRED_KEYS - set(item.keys())
            if missing:
                return [], f"Item {i} missing required keys: {sorted(missing)}"
            item_type = str(item.get("type", "")).strip().lower()
            if item_type not in _VALID_TYPES:
                return [], f"Item {i} has invalid type: {item.get('type')!r}"
            for k in _CONFIDENCE_KEYS:
                v = item.get(k)
                try:
                    fv = float(v)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    return [], f"Item {i} key {k!r} is not a number: {v!r}"
                if not (0.0 <= fv <= 1.0):
                    return [], f"Item {i} key {k!r} out of range [0.0, 1.0]: {fv}"

        got_ids = [str(item.get("id", "")).strip() for item in raw]
        got_set = set(got_ids)
        expected_set = set(expected_ids)

        if len(got_ids) != len(got_set):
            dupes = sorted({id_ for id_ in got_ids if got_ids.count(id_) > 1})
            return [], f"Duplicate ids in response: {dupes}"

        missing_ids = sorted(expected_set - got_set)
        extra_ids = sorted(got_set - expected_set)
        if missing_ids or extra_ids:
            return [], f"ID mismatch — missing: {missing_ids}, extra: {extra_ids}"

        return raw, None  # type: ignore[return-value]

    def _build_required_segment(self, *, segment: Dict[str, Any], classified: Dict[str, Any] | None) -> Dict[str, Any]:
        fallback = {
            "type": "narration",
            "speaker": "narrator",
            "gender": "unknown",
            "speaker_confidence": 0.0,
            "gender_confidence": 0.0,
            "character_confidence": 0.0,
        }
        safe = self._sanitize_llm_output(classified or {}, fallback)
        return {
            "text": str(segment.get("text", "")),
            "type": safe["type"],
            "speaker": safe["speaker"],
            "gender": safe["gender"],
            "speaker_confidence": safe["speaker_confidence"],
            "gender_confidence": safe["gender_confidence"],
            "character_confidence": safe["character_confidence"],
            "paragraph_id": str(segment.get("paragraph_id", "")),
            "voice": str(segment.get("voice", "")),
            "emotion": str(segment.get("emotion", "neutral") or "neutral"),
            "prior_segment_text": str(segment.get("context_before", "")),
            "next_segment_text": str(segment.get("context_after", "")),
        }

    def _normalize_batch_output(self, raw: Any) -> Dict[str, Dict[str, Any]]:
        if isinstance(raw, dict) and isinstance(raw.get("segments"), list):
            raw = raw.get("segments")
        if not isinstance(raw, list):
            return {}
        normalized: Dict[str, Dict[str, Any]] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).strip()
            if not item_id:
                continue
            normalized[item_id] = item
        return normalized

    def _sanitize_llm_output(
        self,
        raw: Dict[str, Any],
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
