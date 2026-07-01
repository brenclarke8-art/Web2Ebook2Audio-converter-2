import json
import logging

from ebook_app.text.identify.speaker_llm import OllamaChatClient


class _Response:
    status_code = 200
    text = '{"response": "{\\"segments\\": []}"}'

    def raise_for_status(self):
        return None

    def json(self):
        return {"response": '{"segments": []}'}


def test_ask_json_applies_context_token_cap(monkeypatch):
    sent_payloads: list[dict] = []

    def _fake_post(_url, *, json, timeout):
        sent_payloads.append(json)
        return _Response()

    monkeypatch.setattr("requests.post", _fake_post)

    client = OllamaChatClient(max_context_tokens=250_000)
    client.ask_json(system="sys", user="hello", chapter_id="ch001")

    assert sent_payloads
    assert sent_payloads[0]["options"]["num_ctx"] == 250_000


def test_ask_json_uses_default_context_token_cap(monkeypatch):
    sent_payloads: list[dict] = []

    def _fake_post(_url, *, json, timeout):
        sent_payloads.append(json)
        return _Response()

    monkeypatch.setattr("requests.post", _fake_post)

    client = OllamaChatClient()
    client.ask_json(system="sys", user="hello", chapter_id="ch001")

    assert sent_payloads
    assert sent_payloads[0]["options"]["num_ctx"] == 250_000


def test_ask_json_debug_logging(monkeypatch, tmp_path, caplog):
    log_file = tmp_path / "llm.jsonl"

    class _VerboseResponse:
        status_code = 200
        text = '{"response": "{\\"segments\\": [{\\"text\\": \\"Hello\\"}]}"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"response": '{"segments": [{"text": "Hello"}]}'}

    def _fake_post(_url, *, json, timeout):
        return _VerboseResponse()

    monkeypatch.setattr("requests.post", _fake_post)

    client = OllamaChatClient(
        base_url="http://example.test/api/generate",
        model="debug:model",
        llm_log_path=str(log_file),
    )

    with caplog.at_level(logging.DEBUG, logger="ebook_app.text.identify.speaker_llm"):
        parsed = client.ask_json(system="sys", user="hello", chapter_id="ch007")

    record = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])
    assert parsed == {"segments": [{"text": "Hello"}]}
    assert record["chapter_id"] == "ch007"
    assert record["url"] == "http://example.test/api/generate"
    assert record["model"] == "debug:model"
    assert record["status_code"] == 200
    assert record["request"]["prompt"].startswith("sys\n\nhello")
    assert record["response_body"] == _VerboseResponse.text
    assert record["response_raw"] == '{"segments": [{"text": "Hello"}]}'
    assert record["parsed"] == parsed
    assert any("LLM request chapter=ch007" in message for message in caplog.messages)
    assert any("LLM response chapter=ch007" in message for message in caplog.messages)
    assert any("LLM parsed response chapter=ch007" in message for message in caplog.messages)
