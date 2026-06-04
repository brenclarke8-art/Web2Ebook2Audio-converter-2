from __future__ import annotations

import json

from ebook_app.models.character_db import Character, CharacterDatabase
from ebook_app.models.dialogue_parser import DialogueParser
from ebook_app.services.dialogue_segmentation_service import DialogueLLMResult, DialogueLLMSegment, DialogueSegmentationService


class _DummyResponse:
    def __init__(self, body: dict):
        self._body = body
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class _CaptureClient:
    def __init__(self):
        self.calls = []

    def ask_json(self, *, system, user, chapter_id):
        self.calls.append({"system": system, "user": user, "chapter_id": chapter_id})
        return {"segments": [], "characters": []}


def test_dialogue_parser_validates_llm_json_contract(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct")
    pass1_payload = [{"line": '"Hello there."', "type": "dialogue"}]
    pass2_payload = [{"line": '"Hello there."', "speaker": "Alice", "Confidence": "0.91"}]

    def _fake_post(*_args, **kwargs):
        prompt = kwargs.get("json", {}).get("prompt", "")
        payload = pass1_payload if "PASS 1" in prompt else pass2_payload
        return _DummyResponse({"response": json.dumps(payload)})

    monkeypatch.setattr("ebook_app.services.llm_client.requests.post", _fake_post)
    result = parser.parse('"Hello there."', chapter_id="ch001")

    assert len(result.segments) == 1
    assert result.segments[0].type == "dialogue"
    assert result.segments[0].speaker == "Alice"
    assert result.detected_characters[0].name == "Alice"


def test_dialogue_parser_cleans_ui_noise_before_prompt(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct")
    captured_payload: dict = {}

    def _fake_post(*_args, **kwargs):
        captured_payload.update(kwargs.get("json", {}))
        return _DummyResponse({"response": json.dumps({"segments": [], "characters": []})})

    monkeypatch.setattr("ebook_app.services.llm_client.requests.post", _fake_post)
    parser.parse(
        "Next Chapter\nSubscribe now\nActual story line.\nAnother story paragraph.",
        chapter_id="ch-clean",
    )

    user_msg = captured_payload.get("prompt", "")
    assert "Next Chapter" not in user_msg
    assert "Subscribe now" not in user_msg
    assert "Actual story line." in user_msg


def test_dialogue_parser_writes_llm_communication_log(monkeypatch, tmp_path):
    log_file = tmp_path / "llm_communication.jsonl"
    parser = DialogueParser(
        ollama_url="http://example/api/generate",
        model="mistral:instruct",
        llm_log_path=str(log_file),
    )

    def _fake_post(*_args, **_kwargs):
        return _DummyResponse({"response": json.dumps({"segments": [], "characters": []})})

    monkeypatch.setattr("ebook_app.services.llm_client.requests.post", _fake_post)
    parser.parse("Story text only.", chapter_id="ch-log")

    lines = [line for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 1
    records = [json.loads(line) for line in lines]
    assert records[0].get("request")
    assert "response_raw" in records[0] or "error" in records[0]


def test_dialogue_parser_falls_back_on_invalid_output(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct")

    def _fake_post(*_args, **_kwargs):
        return _DummyResponse({"response": "not-json"})

    monkeypatch.setattr("ebook_app.services.llm_client.requests.post", _fake_post)
    result = parser.parse("Fallback content.", chapter_id="ch002")

    assert len(result.segments) == 1
    assert result.segments[0].type == "narration"
    assert result.segments[0].speaker == "narrator"


def test_dialogue_parser_accepts_markdown_wrapped_json(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct")
    wrapped_pass1 = """```json
[{"line":"\\"Hi\\"","type":"dialogue"}]
```"""
    wrapped_pass2 = """```json
[{"line":"\\"Hi\\"","speaker":"Alice","Confidence":"0.92"}]
```"""

    def _fake_post(*_args, **kwargs):
        prompt = kwargs.get("json", {}).get("prompt", "")
        wrapped = wrapped_pass1 if "PASS 1" in prompt else wrapped_pass2
        return _DummyResponse({"response": wrapped})

    monkeypatch.setattr("ebook_app.services.llm_client.requests.post", _fake_post)
    result = parser.parse("Story text.", chapter_id="ch-wrap")

    assert result.segments[0].type == "dialogue"
    assert result.segments[0].speaker == "Alice"
    assert any(c.name == "Alice" for c in result.detected_characters)


def test_dialogue_parser_preserves_character_objects(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct")
    pass1_payload = [{"line": '"Hello."', "type": "dialogue"}]
    pass2_payload = [{"line": '"Hello."', "speaker": "Alice", "Confidence": "0.91"}]

    def _fake_post(*_args, **kwargs):
        prompt = kwargs.get("json", {}).get("prompt", "")
        payload = pass1_payload if "PASS 1" in prompt else pass2_payload
        return _DummyResponse({"response": json.dumps(payload)})

    monkeypatch.setattr("ebook_app.services.llm_client.requests.post", _fake_post)
    result = parser.parse("Alice said hello.", chapter_id="ch-characters")

    assert any(c.name == "Alice" for c in result.detected_characters)


def test_dialogue_parser_migrates_chat_endpoint_to_generate():
    parser = DialogueParser(ollama_url="http://127.0.0.1:11434/api/chat", model="mistral")
    assert parser.ollama_url == "http://127.0.0.1:11434/api/generate"


def test_dialogue_parser_keeps_generate_endpoint_unchanged():
    parser = DialogueParser(ollama_url="http://127.0.0.1:11434/api/generate", model="mistral")
    assert parser.ollama_url == "http://127.0.0.1:11434/api/generate"


def test_dialogue_parser_keeps_custom_endpoint_unchanged():
    parser = DialogueParser(ollama_url="http://example.local/custom-endpoint", model="mistral")
    assert parser.ollama_url == "http://example.local/custom-endpoint"


def test_dialogue_parser_canonicalizes_detected_and_segment_speakers(tmp_path, monkeypatch):
    db = CharacterDatabase(path=tmp_path / "character_db.json")
    db.add(
        Character(
            name="Alice",
            voice="af_heart",
            gender="female",
            description="Noblewoman",
            aliases=["Lady Alice"],
        )
    )
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct", character_db=db)

    def _fake_ask_json_any(*, system, user, chapter_id):
        if chapter_id.endswith("_p1"):
            return [{"line": '"Hello."', "type": "dialogue"}]
        if chapter_id.endswith("_p2"):
            return [{"line": '"Hello."', "speaker": "Lady Alice.", "Confidence": "0.7"}]
        return []

    monkeypatch.setattr(parser.client, "ask_json_any", _fake_ask_json_any)
    result = parser.parse("Lady Alice spoke.", chapter_id="ch-canonical")

    assert result.segments[0].speaker == "Alice"
    assert result.segments[0].gender == "female"
    assert len(result.detected_characters) == 1
    assert result.detected_characters[0].name == "Alice"


def test_known_character_context_formatting_includes_alias_gender_and_description():
    context = DialogueSegmentationService._format_known_character_context(
        [
            {
                "name": "Alice",
                "aliases": ["Lady Alice"],
                "gender": "female",
                "description": "Noblewoman",
            }
        ]
    )
    assert "KNOWN CHARACTER CONTEXT" in context
    assert "Alice | aliases=Lady Alice | gender=female | description=Noblewoman" in context


def test_dialogue_segmentation_service_injects_structured_known_character_context():
    client = _CaptureClient()
    service = DialogueSegmentationService(client=client)
    service.parse(
        text="Story text.",
        chapter_id="ch-context",
        known_characters=[
            {
                "name": "Alice",
                "aliases": ["Lady Alice"],
                "gender": "female",
                "description": "Noblewoman",
            }
        ],
    )

    assert client.calls
    system_text = client.calls[0]["system"]
    assert "PASS 1 — Line Classification" in system_text
    assert "CONTEXT (from previous chapters):" in system_text
    assert "KNOWN CHARACTER CONTEXT (canonical names):" in system_text
    assert "Alice | aliases=Lady Alice | gender=female | description=Noblewoman" in system_text


def test_dialogue_segmentation_service_uses_new_system_prompt_contract():
    client = _CaptureClient()
    service = DialogueSegmentationService(client=client)
    service.parse(text="Story text.", chapter_id="ch-prompt")

    assert client.calls
    system_text = client.calls[0]["system"]
    assert system_text.startswith("You are a deterministic text-analysis engine.")
    assert "PASS 1 — Line Classification" in system_text
    assert '[{ "line": "...", "type": "dialogue|thought|narration" }]' in system_text
    assert '"characters": [' not in system_text


def test_dialogue_parser_normalizes_capitalized_unknown_speaker(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct")

    def _fake_ask_json_any(*, system, user, chapter_id):
        if chapter_id.endswith("_p1"):
            return [{"line": '"Hello."', "type": "dialogue"}]
        if chapter_id.endswith("_p2"):
            return [{"line": '"Hello."', "speaker": "Unknown", "Confidence": "0.3"}]
        return []

    monkeypatch.setattr(parser.client, "ask_json_any", _fake_ask_json_any)
    result = parser.parse("Someone spoke.", chapter_id="ch-unknown")

    assert result.segments[0].speaker == "unknown"
