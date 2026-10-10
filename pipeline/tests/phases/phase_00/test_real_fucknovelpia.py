import pytest

from pipeline.phases.phase_00_fetch.runner import run
from pipeline.tests.harness.runner import run_phase


@pytest.mark.live
def test_real_fucknovelpia_site(tmp_path):
    output = run_phase(
        run,
        {"artifact_dir": str(tmp_path)},
        {
            "index_url": "https://fucknovelpia.com/novel/i-became-a-6-gacha-character",
            "chapter_range": [1, 3],
            "settings": {},
            "env": {},
        },
        "phase00_real_fucknovelpia_live",
    )

    if output["errors"]:
        pytest.xfail(f"Live site/network unavailable for real-world test run: {output['errors']}")

    assert output["output_summary"]["chapter_count"] == 3
    assert output["source"]["chapter_range"] == [1, 3]
    assert output["output_summary"]["final_range"] == [1, 3]