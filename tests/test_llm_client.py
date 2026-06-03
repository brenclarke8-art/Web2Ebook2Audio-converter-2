from ebook_app.services.llm_client import OllamaChatClient


class _Response:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": '{"segments": []}'}}


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
