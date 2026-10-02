"""
Phase 06 — Contract Tests
Copilot: Follow Phase 00–05 patterns EXACTLY.
"""

from pipeline.phases.phase_06_audio.output_schema import Phase06Output

def test_contract_fields_exist():
    output = Phase06Output(
        audio_chunks=[],
        audio_index={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={}
    )

    assert hasattr(output, "audio_chunks")
    assert hasattr(output, "audio_index")
    assert hasattr(output, "meta")
