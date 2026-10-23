from pipeline.phases.phase_00_fetch.runner import run as run_phase00
from pipeline.phases.phase_01_source.runner import run as run_phase01
from pipeline.phases.phase_02_cleaning.runner import run as run_phase02
from pipeline.phases.phase_03_segmentation.runner import run as run_phase03
from pipeline.phases.phase_04_character_registry.runner import run as run_phase04
from pipeline.phases.phase_05_semantic_enrichment.runner import run as run_phase05
from pipeline.phases.phase_06_voice_assignment.runner import run as run_phase06
from pipeline.tests.harness.runner import run_phase
from pipeline.tests.phases.phase_00.helpers import read_phase00_fixture


def test_pipeline_00_to_06_with_synthetic_fixtures(monkeypatch, tmp_path):

    index_url = "https://fucknovelpia.com/novel/synthetic-episode-novel"

    index_html = read_phase00_fixture("index_fucknovelpia.html")

    chapter_html = {
        "https://fucknovelpia.com/novel/synthetic-episode-novel/episode-1":
            read_phase00_fixture("chapter_fucknovelpia_1.html"),

        "https://fucknovelpia.com/novel/synthetic-episode-novel/episode-2":
            read_phase00_fixture("chapter_fucknovelpia_2.html"),

        "https://fucknovelpia.com/novel/synthetic-episode-novel/episode-3":
            read_phase00_fixture("chapter_fucknovelpia_3.html"),
    }

    def fake_fetch(url):
        if url == index_url:
            return {
                "ok": True,
                "status": 200,
                "html": index_html,
                "error": None,
            }

        if url in chapter_html:
            return {
                "ok": True,
                "status": 200,
                "html": chapter_html[url],
                "error": None,
            }

        return {
            "ok": False,
            "status": 404,
            "html": "",
            "error": "not mocked",
        }

    monkeypatch.setattr(
        "pipeline.phases.phase_00_fetch.processor.fetch_html",
        fake_fetch,
    )

    #
    # Phase 00
    #

    phase00_output = run_phase(
        run_phase00,
        {"artifact_dir": str(tmp_path)},
        {
            "index_url": index_url,
            "chapter_range": [1, 3],
            "settings": {},
            "env": {},
        },
        "pipeline_synth_phase00",
    )

    assert phase00_output["errors"] == []

    #
    # Phase 01
    #

    phase01_output = run_phase(
        run_phase01,
        {"artifact_root": str(tmp_path)},
        {
            "source": phase00_output["source"],
            "settings": {},
        },
        "pipeline_synth_phase01",
    )

    assert phase01_output["errors"] == []

    #
    # Phase 02
    #

    phase02_output = run_phase(
        run_phase02,
        {"artifact_root": str(tmp_path)},
        {
            "chapter_index": phase01_output["chapter_index"],
            "raw_payloads": phase01_output["raw_payloads"],
            "settings": {},
        },
        "pipeline_synth_phase02",
    )

    assert phase02_output["errors"] == []

    #
    # Phase 03
    #

    phase03_output = run_phase(
        run_phase03,
        {"artifact_root": str(tmp_path)},
        {
            "normalized_chapters": phase02_output["normalized_chapters"],
            "chapter_stats": phase02_output["chapter_stats"],
            "settings": {},
        },
        "pipeline_synth_phase03",
    )

    assert phase03_output["errors"] == []

    #
    # Phase 04
    #

    phase04_output = run_phase(
        run_phase04,
        {"artifact_root": str(tmp_path)},
        {
            "segments": phase03_output["segments"],
            "settings": {},
        },
        "pipeline_synth_phase04",
    )

    assert phase04_output["errors"] == []

    #
    # Phase 05
    #

    phase05_output = run_phase(
        run_phase05,
        {"artifact_root": str(tmp_path)},
        {
            "segments": phase04_output["segments"],
            "character_registry": phase04_output["character_registry"],
            "settings": {},
        },
        "pipeline_synth_phase05",
    )

    assert phase05_output["errors"] == []

    #
    # Phase 06
    #

    phase06_output = run_phase(
        run_phase06,
        {"artifact_root": str(tmp_path)},
        {
            "enriched_segments": phase05_output["enriched_segments"],
            "character_registry": phase05_output["character_registry"],
            "settings": {},
        },
        "pipeline_synth_phase06",
    )

    assert phase06_output["errors"] == []


    #
    # Existing assertions
    #

    assert phase00_output["output_summary"]["chapter_count"] == 3
    assert phase01_output["output_summary"]["chapter_count"] == 3
    assert phase02_output["output_summary"]["normalized_count"] == 3

    assert phase00_output["errors"] == []
    assert phase01_output["errors"] == []
    assert phase02_output["errors"] == []
    assert phase03_output["errors"] == []

    assert phase00_output["output_summary"]["final_range"] == [1, 3]
    assert phase01_output["input_summary"]["source_type"] == "web"
    assert phase02_output["input_summary"]["chapter_count"] == 3

    #
    # New Phase 03 assertions
    #

    assert "segments" in phase03_output
    assert len(phase03_output["segments"]) > 0

    #
    # New Phase 04 assertions
    #

    assert phase04_output["errors"] == []

    assert len(phase04_output["segments"]) > 0
    assert len(phase04_output["character_registry"]) > 0

    #
    # New Phase 05 assertions
    #
    
    assert "enriched_segments" in phase05_output
    assert "character_registry" in phase05_output

    assert len(phase05_output["enriched_segments"]) > 0

    #
    # New Phase 06 assertions
    #

    assert "voice_segments" in phase06_output
    assert "voice_registry" in phase06_output

    assert len(phase06_output["voice_segments"]) > 0
    assert len(phase06_output["voice_registry"]) > 0

    print(
        {
            "phase00_chapters":
                phase00_output["output_summary"]["chapter_count"],

            "phase01_chapters":
                phase01_output["output_summary"]["chapter_count"],

            "phase02_normalized":
                phase02_output["output_summary"]["normalized_count"],

            "phase03_segments":
                len(phase03_output["segments"]),

            "phase04_character_registry":
                len(phase04_output["character_registry"]),
        }
    )