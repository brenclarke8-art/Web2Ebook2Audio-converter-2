from pipeline.phases.phase_02_cleaning.runner import run
from pipeline.tests.harness.runner import run_phase
from pipeline.tests.phases.phase_02.helpers import synthetic_chapter_index


def test_cleaning_removes_boilerplate_navigation_and_formats_consistently(tmp_path):
    raw_payloads = {
        "ch1": (
            "<div class='episode-content'>"
            "<p>Sponsored Content</p>"
            "<p>Episode text first paragraph.</p>"
            "<p>Next Chapter</p>"
            "<p>Episode text second paragraph.</p>"
            "<p>Previous Chapter</p>"
            "</div>"
        ),
        "ch2": (
            "<div class='episode-content'>"
            "<p>   Line one with   extra spacing.   </p>"
            "<p>\n\nLine two after blank lines.\n</p>"
            "</div>"
        ),
        "ch3": "<div class='episode-content'><p>Only body text.</p></div>",
    }

    output = run_phase(
        run,
        {"artifact_root": str(tmp_path)},
        {
            "chapter_index": synthetic_chapter_index(),
            "raw_payloads": raw_payloads,
            "settings": {},
        },
        "phase02_cleaning_rules",
    )

    ch1 = output["normalized_chapters"]["ch1"]
    ch2 = output["normalized_chapters"]["ch2"]

    # Boilerplate removal
    assert "Sponsored Content" not in ch1

    # Navigation text removal
    assert "Next Chapter" not in ch1
    assert "Previous Chapter" not in ch1

    # Consistent formatting
    assert "  " not in ch2
    assert "\n\n\n" not in ch2