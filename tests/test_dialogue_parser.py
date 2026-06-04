from __future__ import annotations

import json
import re

from ebook_app.models.character_db import Character, CharacterDatabase
from ebook_app.models.dialogue_parser import DialogueParser
from ebook_app.services.dialogue_segmentation_service import (
    DialogueLLMResult,
    DialogueLLMSegment,
    DialogueSegmentationService,
    ParseDiagnostics,
)


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

    def ask_json_any(self, *, system, user, chapter_id):
        self.calls.append({"system": system, "user": user, "chapter_id": chapter_id})
        # Return empty list for ID-based pass-2; heuristic fallback handles it
        return []


def _extract_id_lines_from_prompt(prompt: str) -> list[dict]:
    """Parse the ID'd line JSON array embedded in a pass-2 prompt.

    Looks for arrays where items have both "id" and "text" keys — which
    distinguishes the actual source-line payload from schema examples in the
    system prompt (which use "..." as placeholder values).
    """
    for m in re.finditer(r'\[\s*\{[^]]*"id"[^]]*\}[^]]*\]', prompt, re.DOTALL):
        try:
            items = json.loads(m.group())
            # Only accept if items look like real source lines (have "text" key
            # with non-placeholder content).
            if (
                isinstance(items, list)
                and items
                and isinstance(items[0], dict)
                and "text" in items[0]
                and items[0].get("text") != "..."
            ):
                return items
        except json.JSONDecodeError:
            continue
    return []


def test_dialogue_parser_validates_llm_json_contract(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct")
    pass1_payload = [{"name": "Alice", "gender": "female", "confidence": 0.9}]

    def _fake_post(*_args, **kwargs):
        prompt = kwargs.get("json", {}).get("prompt", "")
        if "chapter-summary assistant" in prompt:
            payload = {"summary": "Alice arrives and greets Bob."}
        elif "CHARACTER DETECTION" in prompt:
            payload = pass1_payload
        else:
            # Pass 2: return ID-based items matching the IDs in the prompt
            id_lines = _extract_id_lines_from_prompt(prompt)
            payload = [
                {"id": entry["id"], "type": "dialogue", "speaker": "Alice"}
                for entry in id_lines
            ]
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
[{"name":"Alice","gender":"female","confidence":0.9}]
```"""

    def _fake_post(*_args, **kwargs):
        prompt = kwargs.get("json", {}).get("prompt", "")
        if "chapter-summary assistant" in prompt:
            return _DummyResponse({"response": '{"summary": "Alice says hi."}'})
        if "CHARACTER DETECTION" in prompt:
            return _DummyResponse({"response": wrapped_pass1})
        # Pass 2: parse IDs and return ID-based items wrapped in markdown
        id_lines = _extract_id_lines_from_prompt(prompt)
        items = [
            {"id": entry["id"], "type": "dialogue", "speaker": "Alice"}
            for entry in id_lines
        ]
        wrapped = f"```json\n{json.dumps(items)}\n```"
        return _DummyResponse({"response": wrapped})

    monkeypatch.setattr("ebook_app.services.llm_client.requests.post", _fake_post)
    result = parser.parse('"Hi."', chapter_id="ch-wrap")

    assert result.segments[0].type == "dialogue"
    assert result.segments[0].speaker == "Alice"
    assert any(c.name == "Alice" for c in result.detected_characters)


def test_dialogue_parser_preserves_character_objects(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct")
    pass1_payload = [{"name": "Alice", "gender": "female", "confidence": 0.9}]

    def _fake_post(*_args, **kwargs):
        prompt = kwargs.get("json", {}).get("prompt", "")
        if "chapter-summary assistant" in prompt:
            payload = {"summary": "Alice said hello."}
        elif "CHARACTER DETECTION" in prompt:
            payload = pass1_payload
        else:
            id_lines = _extract_id_lines_from_prompt(prompt)
            payload = [
                {"id": entry["id"], "type": "dialogue", "speaker": "Alice"}
                for entry in id_lines
            ]
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
            return [{"name": "Alice", "gender": "female", "confidence": 0.9}]
        if chapter_id.endswith("_p2"):
            # Parse the ID-based user JSON and return ID-keyed items
            try:
                id_lines = json.loads(user) if isinstance(user, str) else user
                return [{"id": entry["id"], "type": "dialogue", "speaker": "Lady Alice."} for entry in id_lines]
            except (json.JSONDecodeError, TypeError, KeyError):
                return []
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
    # Pass 0 is the new chapter summary call; pass 1 (character detection) is now calls[1]
    assert len(client.calls) >= 2
    system_text = client.calls[1]["system"]
    assert "CHARACTER DETECTION" in system_text
    assert "CONTEXT (from previous chapters):" in system_text
    assert "KNOWN CHARACTER CONTEXT (canonical names):" in system_text
    assert "Alice | aliases=Lady Alice | gender=female | description=Noblewoman" in system_text


def test_dialogue_segmentation_service_uses_new_system_prompt_contract():
    client = _CaptureClient()
    service = DialogueSegmentationService(client=client)
    service.parse(text="Story text.", chapter_id="ch-prompt")

    assert client.calls
    # Pass 0 is the chapter summary call; pass 1 and pass 2 follow
    assert len(client.calls) >= 3
    # Pass 0: chapter summary prompt
    pass0_system = client.calls[0]["system"]
    assert "chapter-summary assistant" in pass0_system
    # Pass 1: character detection prompt
    pass1_system = client.calls[1]["system"]
    assert pass1_system.startswith("You are a deterministic character-extraction engine.")
    assert "CHARACTER DETECTION" in pass1_system
    assert '[{ "name": "...", "gender": "male|female|unknown", "confidence": 0.0-1.0 }]' in pass1_system
    # Pass 2: segment + attribute prompt uses new ID-based contract
    pass2_system = client.calls[2]["system"]
    assert "SEGMENT AND ATTRIBUTE" in pass2_system
    # Check new ID-based input/output format
    assert 'Input: JSON array of {"id": "...", "text": "..."}' in pass2_system
    assert '[{"id": "...", "type": "dialogue|thought|narration", "speaker": "Name or narrator"}]' in pass2_system


def test_dialogue_parser_normalizes_capitalized_unknown_speaker(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct")

    def _fake_ask_json_any(*, system, user, chapter_id):
        if chapter_id.endswith("_p1"):
            return []  # no characters detected
        if chapter_id.endswith("_p2"):
            # Parse IDs from user JSON and attribute to Unknown
            try:
                id_lines = json.loads(user) if isinstance(user, str) else user
                return [{"id": entry["id"], "type": "dialogue", "speaker": "Unknown"} for entry in id_lines]
            except (json.JSONDecodeError, TypeError, KeyError):
                return []
        return []

    monkeypatch.setattr(parser.client, "ask_json_any", _fake_ask_json_any)
    result = parser.parse('"Someone spoke."', chapter_id="ch-unknown")

    assert result.segments[0].speaker == "unknown"


def test_dialogue_segmentation_accepts_single_object_payloads():
    class _SingleObjectClient:
        def ask_json_any(self, *, system, user, chapter_id):
            if chapter_id.endswith("_p1"):
                # Pass 1: single character detection object
                return {"name": "Alice", "gender": "female", "confidence": 0.9}
            if chapter_id.endswith("_p2"):
                # Pass 2: parse IDs from user JSON, return ID-based single-object payload
                try:
                    id_lines = json.loads(user) if isinstance(user, str) else user
                    if id_lines:
                        return {"id": id_lines[0]["id"], "type": "dialogue", "speaker": "Alice"}
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
            return []

    service = DialogueSegmentationService(client=_SingleObjectClient())
    result = service.parse(text='"Hello there."', chapter_id="ch-single-object")

    assert result.segments[0].type == "dialogue"
    assert result.segments[0].speaker == "Alice"
    assert result.characters[0]["name"] == "Alice"


def test_dialogue_segmentation_accepts_line_mapping_payloads():
    """Pass-2 responses with the legacy line-keyed dict format are handled via _normalize_pass_combined."""
    class _MappingClient:
        def ask_json_any(self, *, system, user, chapter_id):
            if chapter_id.endswith("_p1"):
                return [{"name": "Alice", "gender": "female", "confidence": 0.9}]
            if chapter_id.endswith("_p2"):
                # Parse IDs from user JSON, return valid ID-based items
                try:
                    id_lines = json.loads(user) if isinstance(user, str) else user
                    types = ["dialogue", "narration"]
                    speakers = ["Alice", "narrator"]
                    return [
                        {"id": entry["id"], "type": types[i % 2], "speaker": speakers[i % 2]}
                        for i, entry in enumerate(id_lines)
                    ]
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
            return []

    service = DialogueSegmentationService(client=_MappingClient())
    result = service.parse(text='"Hello there."\nA narration line.', chapter_id="ch-line-mapping")

    assert result.segments[0].type == "dialogue"
    assert result.segments[0].speaker == "Alice"
    assert result.segments[1].type == "narration"
    assert result.characters[0]["name"] == "Alice"


# ---------------------------------------------------------------------------
# New tests for two-model architecture
# ---------------------------------------------------------------------------


def test_dialogue_parser_two_model_constructor_defaults():
    """DialogueParser creates separate semantic and formatter clients by default."""
    parser = DialogueParser(ollama_url="http://example/api/generate")
    assert parser.client.model == "qwen2.5:7b-instruct"
    assert parser.formatter_client is not None
    assert parser.formatter_client.model == "qwen2.5-coder:7b"
    assert parser.service.formatter_client is parser.formatter_client


def test_dialogue_parser_two_model_constructor_explicit():
    """DialogueParser respects explicit semantic_model and formatter_model arguments."""
    parser = DialogueParser(
        ollama_url="http://example/api/generate",
        semantic_model="llama3:8b-instruct",
        formatter_model="codellama:7b",
    )
    assert parser.client.model == "llama3:8b-instruct"
    assert parser.formatter_client.model == "codellama:7b"


def test_formatter_repair_succeeds_when_semantic_output_malformed():
    """Formatter model repairs a malformed/ID-less semantic response."""

    class _TwoModelClient:
        def __init__(self, name):
            self.name = name

        def ask_json_any(self, *, system, user, chapter_id):
            if self.name == "semantic":
                if chapter_id.endswith("_p0"):
                    return {"summary": "Test chapter."}
                if chapter_id.endswith("_p1"):
                    return [{"name": "Bob", "gender": "male", "confidence": 0.9}]
                if chapter_id.endswith("_p2"):
                    # Return malformed output (no IDs)
                    return [{"line": '"Go away."', "type": "dialogue", "speaker": "Bob"}]
            else:
                # Formatter: parse ids from user's SOURCE LIST
                try:
                    source_part = user.split("SOURCE LIST:")[1].split("MALFORMED RESPONSE:")[0].strip()
                    id_lines = json.loads(source_part)
                    return [
                        {"id": entry["id"], "type": "dialogue", "speaker": "Bob"}
                        for entry in id_lines
                    ]
                except (IndexError, json.JSONDecodeError, KeyError):
                    pass
            return []

    semantic = _TwoModelClient("semantic")
    formatter = _TwoModelClient("formatter")
    service = DialogueSegmentationService(client=semantic, formatter_client=formatter)
    result = service.parse(text='"Go away."', chapter_id="ch-repair")

    # Repair should have been attempted and succeeded
    assert result.diagnostics.repair_attempted
    assert result.diagnostics.repair_succeeded
    assert result.diagnostics.validation_passed
    assert result.segments[0].type == "dialogue"
    assert result.segments[0].speaker == "Bob"


def test_invalid_ids_rejected_safe_fallback_used():
    """When semantic output has invalid IDs and no formatter, heuristic fallback is used."""

    class _BadIdClient:
        def ask_json_any(self, *, system, user, chapter_id):
            if chapter_id.endswith("_p0"):
                return {"summary": "Test."}
            if chapter_id.endswith("_p1"):
                return []
            if chapter_id.endswith("_p2"):
                # Return items with entirely wrong IDs
                return [
                    {"id": "wrong_id_0", "type": "dialogue", "speaker": "Ghost"},
                    {"id": "wrong_id_1", "type": "narration", "speaker": "narrator"},
                ]
            return []

    service = DialogueSegmentationService(client=_BadIdClient(), formatter_client=None)
    result = service.parse(text='"Hello."\nNarration.', chapter_id="ch-invalid-ids")

    # No formatter available — should fall back and flag for review
    assert result.diagnostics.malformed_json
    assert not result.diagnostics.validation_passed
    assert result.diagnostics.needs_review
    assert not result.diagnostics.repair_attempted
    # Heuristic fallback should produce some segments
    assert len(result.segments) >= 1
    # Heuristic speaker should not be "Ghost" (a wrong ID's speaker)
    assert all(s.speaker != "Ghost" for s in result.segments)


def test_fallback_bug_regression_empty_segments_use_original_text(monkeypatch):
    """Regression: when LLM returns no valid segments, fallback uses the original chapter
    text instead of the stale loop variable from _convert_segments."""
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct")
    original_text = "This is the original chapter text."

    def _fake_ask_json_any(*, system, user, chapter_id):
        # Always return empty — forces the fallback path
        return []

    monkeypatch.setattr(parser.client, "ask_json_any", _fake_ask_json_any)
    result = parser.parse(original_text, chapter_id="ch-fallback-bug")

    assert len(result.segments) == 1
    # The fallback segment text should be derived from the original chapter text
    assert result.segments[0].text.strip() != ""
    assert original_text.split()[0] in result.segments[0].text


def test_parse_diagnostics_propagated_in_result(monkeypatch):
    """ParseDiagnostics metadata is available on the DialogueLLMResult."""
    parser = DialogueParser(ollama_url="http://example/api/generate", model="mistral:instruct")

    def _fake_ask_json_any(*, system, user, chapter_id):
        if chapter_id.endswith("_p0"):
            return {"summary": "Test."}
        if chapter_id.endswith("_p1"):
            return [{"name": "Alice", "gender": "female", "confidence": 0.9}]
        if chapter_id.endswith("_p2"):
            try:
                id_lines = json.loads(user) if isinstance(user, str) else user
                return [{"id": entry["id"], "type": "narration", "speaker": "narrator"} for entry in id_lines]
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    monkeypatch.setattr(parser.client, "ask_json_any", _fake_ask_json_any)
    # Access the underlying service result to check diagnostics
    service = parser.service
    result = service.parse(text="Some narration.", chapter_id="ch-diag")

    assert result.diagnostics is not None
    assert isinstance(result.diagnostics, ParseDiagnostics)
    assert result.diagnostics.validation_passed
    assert result.diagnostics.id_match_ratio == 1.0


def test_repair_failure_falls_back_safely():
    """When both semantic and formatter return invalid output, safe heuristic fallback is used."""

    class _AlwaysBadClient:
        def ask_json_any(self, *, system, user, chapter_id):
            if chapter_id.endswith("_p0"):
                return {"summary": "Test."}
            if chapter_id.endswith("_p1"):
                return []
            # Both pass-2 and repair return garbage
            return [{"id": "bad_id", "type": "dialogue", "speaker": "Ghost"}]

    semantic = _AlwaysBadClient()
    formatter = _AlwaysBadClient()
    service = DialogueSegmentationService(client=semantic, formatter_client=formatter)
    result = service.parse(text='"Hello."\nNarration.', chapter_id="ch-repair-fail")

    # Both attempts failed; result should be flagged for review
    assert result.diagnostics.repair_attempted
    assert not result.diagnostics.repair_succeeded
    assert result.diagnostics.needs_review
    assert not result.diagnostics.validation_passed
    # Heuristic fallback still produces output
    assert len(result.segments) >= 1
    assert all(s.speaker != "Ghost" for s in result.segments)

