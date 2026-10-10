from pipeline.tests.harness.utils import tests_root


def read_phase00_fixture(name: str) -> str:
    path = tests_root() / "fixtures" / "phase_00" / name
    return path.read_text(encoding="utf-8")
