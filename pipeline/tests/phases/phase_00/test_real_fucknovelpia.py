import pytest

from pipeline.phases.phase_00_fetch.runner import run
from pipeline.tests.harness.runner import run_phase


def _is_live_network_error(errors):
    joined = " | ".join(errors)
    network_indicators = [
        "Failed to fetch index URL",
        "Connection",
        "timed out",
        "SSL",
        "Name or service not known",
        "Temporary failure in name resolution",
        "HTTP 5",
    ]
    return any(indicator in joined for indicator in network_indicators)


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

    if output["errors"] and _is_live_network_error(output["errors"]):
        pytest.xfail(f"Live site/network unavailable for real-world test run: {output['errors']}")

    assert output["output_summary"]["chapter_count"] == 3
    assert output["errors"] == []
    assert output["source"]["chapter_range"] == [1, 3]
    assert output["output_summary"]["final_range"] == [1, 3]