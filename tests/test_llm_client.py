from ebook_app.text.identify.speaker_llm import OllamaChatClient


class _Response:
    status_code = 200

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
