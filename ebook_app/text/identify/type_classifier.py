from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

import requests


@dataclass
class LLMClient:
    base_url: str
    model: str
    timeout: int = 120
    retries: int = 1
    provider: str = "ollama_local"
    api_key: str = ""

    def generate_json(self, *, system: str, user: str) -> Dict[str, Any] | List[Dict[str, Any]]:
        payload, headers = self._build_request(system=system, user=user)
        last_error = None

        for attempt in range(self.retries + 1):
            try:
                resp = requests.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                return self._parse_response(resp.json())
            except Exception as exc:
                last_error = str(exc)
                if attempt >= self.retries:
                    break

        return {}

    def classify(self, prompt: str) -> Dict[str, Any]:
        result = self.generate_json(system="Return JSON only.", user=prompt)
        return result if isinstance(result, dict) else {}

    def _build_request(self, *, system: str, user: str) -> tuple[dict[str, Any], dict[str, str]]:
        provider = (self.provider or "ollama_local").strip().lower()
        if provider == "external_cloud":
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
                headers["Authorization"] = "Bearer " + self.api_key
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
            }
            return payload, headers
        payload = {
            "model": self.model,
            "prompt": f"{system}\n\n{user}",
            "system": system,
            "stream": False,
        }
        return payload, {}

    @staticmethod
    def _parse_json_text(raw: Any) -> Any:
        if isinstance(raw, (dict, list)):
            return raw
        text = "" if raw is None else str(raw).strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return json.loads(text) if text else {}

    def _parse_response(self, data: Any) -> Dict[str, Any] | List[Dict[str, Any]]:
        if isinstance(data, dict) and "response" in data:
            try:
                parsed = self._parse_json_text(data["response"])
                if isinstance(parsed, (dict, list)):
                    return parsed
            except Exception:
                return {}
        if isinstance(data, dict) and "choices" in data:
            choices = data.get("choices", [])
            if choices and isinstance(choices[0], dict):
                content = choices[0].get("message", {}).get("content", "")
                try:
                    parsed = self._parse_json_text(content)
                    if isinstance(parsed, (dict, list)):
                        return parsed
                except Exception:
                    return {}
        if isinstance(data, (dict, list)):
            return data
        return {}


class Pass2Classifier:
    def __init__(self, llm_client: LLMClient, batch_size: int = 20) -> None:
        self.llm_client = llm_client
        self.batch_size = max(1, int(batch_size))

    def classify_segment(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        return self.classify_segments([segment])[0]

    def classify_segments(
        self,
        segments: List[Dict[str, Any]],
        chapter_id: str = "",
        should_cancel=None,
    ) -> List[Dict[str, Any]]:
        if not segments:
            return []

        output: List[Dict[str, Any]] = []
        for start in range(0, len(segments), self.batch_size):
            if callable(should_cancel) and should_cancel():
                break
            batch = segments[start : start + self.batch_size]
            output.extend(self._classify_batch(batch=batch, chapter_id=chapter_id, offset=start))
        return output

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
        entries = []
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

        system = (
            "You are a semantic classifier for novel text. "
            "Return ONLY JSON array with one object per input id. "
            "Each object must include keys: id, type, speaker, gender, "
            "speaker_confidence, gender_confidence, character_confidence. "
            "Allowed type values: dialogue, thought, narration. "
            "Confidence values must be numbers between 0.0 and 1.0."
        )
        user = json.dumps(entries, ensure_ascii=False)
        raw = self.llm_client.generate_json(system=system, user=user)
        by_id = self._normalize_batch_output(raw)

        out: List[Dict[str, Any]] = []
        for idx, segment in enumerate(batch):
            entry_id = entries[idx]["id"]
            out.append(self._build_required_segment(segment=segment, classified=by_id.get(entry_id)))
        return out

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
