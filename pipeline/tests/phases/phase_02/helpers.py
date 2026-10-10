import json

from pipeline.tests.harness.utils import tests_root


def load_phase02_raw_payloads_fixture():
    path = tests_root() / "fixtures" / "phase_02" / "raw_payloads_synthetic.json"
    return json.loads(path.read_text(encoding="utf-8"))


def synthetic_chapter_index():
    return [
        {"chapter_id": "ch1", "title": "Episode 1", "order": 1},
        {"chapter_id": "ch2", "title": "Episode 2", "order": 2},
        {"chapter_id": "ch3", "title": "Episode 3", "order": 3},
    ]
