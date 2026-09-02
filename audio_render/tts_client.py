# ebook_app/tts/tts_client.py
from __future__ import annotations

from pathlib import Path

import requests


class TTSClient:
    def __init__(self, base_url: str = 'http://127.0.0.1:5005', timeout: float = 10):
        self.base_url = base_url.rstrip('/')
        self.timeout = float(timeout)

    def health(self) -> dict:
        try:
            response = requests.get(f'{self.base_url}/health', timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {'status': 'ok'}
        except Exception as exc:
            return {'status': 'error', 'error': str(exc)}

    def preview(self, voice: str, speed: float = 1.0) -> dict:
        return self.synthesize(
            text='This is a preview of the selected voice.',
            voice=voice,
            speed=speed,
            output_filename='preview.wav',
        )

    def synthesize(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_filename: str = 'preview.wav',
    ) -> dict:
        payload = {
            'text': text,
            'voice': voice,
            'speed': float(speed),
            'output_filename': output_filename,
        }
        try:
            response = requests.post(f'{self.base_url}/synthesize', json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            result = {'status': 'ok'}
            if isinstance(data, dict):
                result.update(data)
            return result
        except Exception as exc:
            return {'status': 'error', 'error': str(exc), 'output_filename': output_filename}
