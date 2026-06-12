"""Tests for the experimental StoryContextService and StoryContext data model."""

from __future__ import annotations

from ebook_app.services.story_context_service import (
    StoryContext,
    StoryContextService,
    _MAX_SUMMARY_CHARS,
)


# ── StoryContext data-model tests ─────────────────────────────────────────────


def test_story_context_default_is_empty():
    ctx = StoryContext()
    assert ctx.is_empty()
    assert ctx.summary == ""
    assert ctx.active_characters == []
    assert ctx.last_chapter_id == ""


def test_story_context_to_prompt_block_empty():
    ctx = StoryContext()
    assert ctx.to_prompt_block() == ""


def test_story_context_to_prompt_block_with_content():
    ctx = StoryContext(
        summary="Alice and Bob travel to the mountains.",
        active_characters=["Alice", "Bob"],
        last_chapter_id="ch001",
    )
    block = ctx.to_prompt_block()
    assert "Alice" in block
    assert "Bob" in block
    assert "Alice and Bob travel to the mountains." in block
    assert "STORY CONTEXT" in block


def test_story_context_to_prompt_block_no_characters():
    ctx = StoryContext(summary="The hero journeys onward.", active_characters=[])
    block = ctx.to_prompt_block()
    assert "The hero journeys onward." in block
    assert "Active characters" not in block


def test_story_context_round_trip_dict():
    ctx = StoryContext(
        summary="A short summary.",
        active_characters=["Alice", "Bob"],
        last_chapter_id="ch002",
    )
    restored = StoryContext.from_dict(ctx.to_dict())
    assert restored.summary == ctx.summary
    assert restored.active_characters == ctx.active_characters
    assert restored.last_chapter_id == ctx.last_chapter_id


def test_story_context_from_dict_non_list_active_characters():
    restored = StoryContext.from_dict(
        {
            "summary": "A summary.",
            "active_characters": "Alice",
            "last_chapter_id": "ch001",
        }
    )
    assert restored.summary == "A summary."
    assert restored.active_characters == []
    assert restored.last_chapter_id == "ch001"


def test_story_context_load_missing_file(tmp_path):
    ctx = StoryContext.load(tmp_path / "nonexistent.json")
    assert ctx.is_empty()


def test_story_context_load_corrupt_file(tmp_path):
    path = tmp_path / "story_context.json"
    path.write_text("not valid json", encoding="utf-8")
    ctx = StoryContext.load(path)
    assert ctx.is_empty()


def test_story_context_save_and_reload(tmp_path):
    path = tmp_path / "story_context.json"
    ctx = StoryContext(
        summary="The village was burned.",
        active_characters=["Hero", "Villain"],
        last_chapter_id="ch003",
    )
    ctx.save(path)
    assert path.exists()
    loaded = StoryContext.load(path)
    assert loaded.summary == ctx.summary
    assert loaded.active_characters == ctx.active_characters
    assert loaded.last_chapter_id == ctx.last_chapter_id


def test_story_context_save_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "deep" / "story_context.json"
    ctx = StoryContext(summary="Test summary.", active_characters=[])
    ctx.save(path)
    assert path.exists()


# ── StoryContextService tests ─────────────────────────────────────────────────


class _FakeClient:
    """Fake OllamaChatClient that returns a scripted response."""

    def __init__(self, response: dict):
        self._response = response
        self.calls: list[dict] = []

    def ask_json(self, *, system: str, user: str, chapter_id: str) -> dict:
        self.calls.append({"system": system, "user": user, "chapter_id": chapter_id})
        return self._response


def test_service_update_creates_new_context():
    client = _FakeClient(
        {
            "summary": "Alice defeats the dragon.",
            "active_characters": ["Alice", "Dragon"],
        }
    )
    svc = StoryContextService(client=client)
    ctx = svc.update_from_chapter(
        chapter_text="Alice raised her sword and slew the dragon.",
        chapter_id="ch001",
    )
    assert ctx.summary == "Alice defeats the dragon."
    assert "Alice" in ctx.active_characters
    assert ctx.last_chapter_id == "ch001"


def test_service_update_includes_prior_context_in_prompt():
    client = _FakeClient(
        {
            "summary": "Alice and Bob reach the castle.",
            "active_characters": ["Alice", "Bob"],
        }
    )
    prior = StoryContext(
        summary="Alice set off on the quest.",
        active_characters=["Alice"],
        last_chapter_id="ch001",
    )
    svc = StoryContextService(client=client)
    svc.update_from_chapter(
        chapter_text="Bob joined Alice on the road.",
        chapter_id="ch002",
        prior_context=prior,
    )
    assert len(client.calls) == 1
    user_text = client.calls[0]["user"]
    assert "Alice set off on the quest." in user_text
    assert "Alice" in user_text


def test_service_update_returns_fallback_on_llm_error():
    class _ErrorClient:
        def ask_json(self, **_kwargs):
            raise RuntimeError("LLM unreachable")

    prior = StoryContext(
        summary="Prior summary.", active_characters=["Hero"], last_chapter_id="ch001"
    )
    svc = StoryContextService(client=_ErrorClient())
    ctx = svc.update_from_chapter(
        chapter_text="Some text.", chapter_id="ch002", prior_context=prior
    )
    # Must fall back to prior_context
    assert ctx.summary == prior.summary
    assert ctx.active_characters == prior.active_characters


def test_service_update_returns_empty_fallback_on_llm_error_no_prior():
    class _ErrorClient:
        def ask_json(self, **_kwargs):
            raise RuntimeError("LLM unreachable")

    svc = StoryContextService(client=_ErrorClient())
    ctx = svc.update_from_chapter(chapter_text="Some text.", chapter_id="ch001")
    assert ctx.is_empty()


def test_service_update_caps_summary_length():
    very_long_summary_input = "word " * 200  # far longer than _MAX_SUMMARY_CHARS
    client = _FakeClient(
        {
            "summary": very_long_summary_input,
            "active_characters": [],
        }
    )
    svc = StoryContextService(client=client)
    ctx = svc.update_from_chapter(chapter_text="Chapter text.", chapter_id="ch001")
    assert len(ctx.summary) <= _MAX_SUMMARY_CHARS


def test_service_update_caps_summary_length_without_spaces():
    very_long_summary_input = "x" * (_MAX_SUMMARY_CHARS + 50)
    client = _FakeClient(
        {
            "summary": very_long_summary_input,
            "active_characters": [],
        }
    )
    svc = StoryContextService(client=client)
    ctx = svc.update_from_chapter(chapter_text="Chapter text.", chapter_id="ch001")
    assert len(ctx.summary) <= _MAX_SUMMARY_CHARS


def test_service_update_handles_empty_llm_summary():
    client = _FakeClient({"summary": "", "active_characters": []})
    prior = StoryContext(summary="Prior summary.", active_characters=[])
    svc = StoryContextService(client=client)
    ctx = svc.update_from_chapter(
        chapter_text="Text.", chapter_id="ch001", prior_context=prior
    )
    # Empty summary → keep prior context
    assert ctx.summary == "Prior summary."


def test_service_chapter_id_appends_ctx_suffix():
    client = _FakeClient({"summary": "Summary.", "active_characters": []})
    svc = StoryContextService(client=client)
    svc.update_from_chapter(chapter_text="Text.", chapter_id="ch005")
    assert client.calls[0]["chapter_id"] == "ch005_ctx"


def test_service_truncates_long_chapter_text():
    long_text = "x" * 10_000
    captured = {}

    class _CapturingClient:
        def ask_json(self, *, system, user, chapter_id):
            captured["user"] = user
            return {"summary": "S.", "active_characters": []}

    svc = StoryContextService(client=_CapturingClient())
    svc.update_from_chapter(chapter_text=long_text, chapter_id="ch001")
    # Truncated chapter text must be shorter than the original
    assert len(captured["user"]) < len(long_text)


# ── Integration: StoryContext injected into DialogueSegmentationService ───────


def test_segmentation_service_receives_story_context(monkeypatch):
    """Story context block should be inserted into pass-1 (character detection) system prompt."""
    from ebook_app.text.segment.segmenter import (
        DialogueSegmentationService,
    )

    calls: list[dict] = []

    class _CapClient:
        def ask_json(self, *, system, user, chapter_id):
            calls.append({"system": system, "user": user, "chapter_id": chapter_id})
            return {"segments": [], "characters": []}

    svc = DialogueSegmentationService(client=_CapClient())
    ctx_block = "STORY CONTEXT (from prior chapters — use for continuity only):\nAlice set off."
    svc.parse(
        text="Alice arrived at the castle.",
        chapter_id="ch002",
        story_context_block=ctx_block,
    )
    # Story context feeds pass 1 (character detection) only
    pass1_call = next(c for c in calls if c["chapter_id"].endswith("_p1"))
    assert ctx_block in pass1_call["system"]
    assert "Alice arrived at the castle." in pass1_call["user"]
    # Pass 2 (segment + attribute) must NOT receive the story context
    pass2_call = next(c for c in calls if c["chapter_id"].endswith("_p2"))
    assert ctx_block not in pass2_call["system"]


def test_segmentation_service_no_story_context_unchanged(monkeypatch):
    """Without story context, the user message should not contain context headers."""
    from ebook_app.text.segment.segmenter import (
        DialogueSegmentationService,
    )

    captured: dict = {}

    class _CapClient:
        def ask_json(self, *, system, user, chapter_id):
            captured["user"] = user
            return {"segments": [], "characters": []}

    svc = DialogueSegmentationService(client=_CapClient())
    svc.parse(
        text="Bob walked through the forest.",
        chapter_id="ch001",
    )
    assert "STORY CONTEXT" not in captured["user"]
    assert "Bob walked through the forest." in captured["user"]
