from pipeline.phases.phase_00_fetch.runner import run

def test_runner_executes():
    context = {"artifact_dir": "tmp"}
    input_artifact = {
        "index_url": "https://example.com",
        "chapter_range": [1, 1],
        "settings": {},
        "env": {}
    }
    out = run(context, input_artifact)
    assert isinstance(out, dict)
