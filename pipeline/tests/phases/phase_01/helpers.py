import json

from pipeline.tests.harness.utils import tests_root


def load_phase01_source_fixture():
    path = tests_root() / "fixtures" / "phase_01" / "source_synthetic.json"
    return json.loads(path.read_text(encoding="utf-8"))
