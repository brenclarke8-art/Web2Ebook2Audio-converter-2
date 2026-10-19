from pipeline.phases.phase_06_tts.runner import run


def test_runner_executes(tmp_path):
    context = {"artifact_root": str(tmp_path)}
    input_artifact = {
        "enriched_segments": [
            {
                "segment_id": "seg1",
                "text": "Hello",
                "segment_type": "narration",
                "speaker_id": None,
                "thought_owner_id": None,
                "referenced_characters": [],
                "confidence": 0.7,
            }
        ],
        "character_registry": [],
        "settings": {"config_version": "1.0"},
    }

    output = run(context, input_artifact)
    assert "meta" in output
    assert "voice_registry" in output
