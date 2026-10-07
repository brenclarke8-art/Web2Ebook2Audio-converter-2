from pipeline.phases.phase_00_fetch.processor import process
from pipeline.phases.phase_00_fetch.input_schema import Phase00FetchInput

def test_processor_runs_minimal():
    inp = Phase00FetchInput(
        index_url="https://example.com",
        chapter_range=[1, 1],
        settings={},
        env={}
    )
    out = process(inp)
    assert hasattr(out, "source")
    assert hasattr(out, "warnings")
