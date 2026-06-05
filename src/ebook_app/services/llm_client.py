from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests


class OllamaChatClient:
    def __init__(
        self,
        *,
        base_url: str = 'http://127.0.0.1:11434/api/generate',
        model: str = 'qwen2.5-coder:7b',
        max_context_tokens: int = 250_000,
        timeout: int = 300,
        retries: int = 1,
        llm_log_path: str | None = None,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.max_context_tokens = int(max_context_tokens)
        self.timeout = int(timeout)
        self.retries = max(1, int(retries))
        self.llm_log_path = Path(llm_log_path) if llm_log_path else None

    def _log(self, record: dict[str, Any]) -> None:
        if not self.llm_log_path:
            return
        self.llm_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.llm_log_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')

    @staticmethod
    def _parse_json_text(raw: Any) -> Any:
        if isinstance(raw, (dict, list)):
            return raw
        text = '' if raw is None else str(raw).strip()
        if text.startswith('```'):
            lines = text.splitlines()
            if lines and lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            text = '\n'.join(lines).strip()
        return json.loads(text)

    def ask_json_any(self, *, system: str, user: str, chapter_id: str) -> Any:
        payload = {
            'model': self.model,
            'prompt': f'{system}\n\n{user}',
            'system': system,
            'stream': False,
            'options': {'num_ctx': self.max_context_tokens},
        }
        last_error: Exception | None = None
        for _attempt in range(self.retries):
            try:
                response = requests.post(self.base_url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                body = response.json()
                raw = body.get('response', '')
                parsed = self._parse_json_text(raw)
                self._log({'chapter_id': chapter_id, 'request': payload, 'response_raw': raw})
                return parsed
            except Exception as exc:
                last_error = exc
                self._log({'chapter_id': chapter_id, 'request': payload, 'error': str(exc)})
        assert last_error is not None
        raise last_error

    def ask_json(self, *, system: str, user: str, chapter_id: str) -> Any:
        return self.ask_json_any(system=system, user=user, chapter_id=chapter_id)
