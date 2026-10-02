"""
Phase 06 — Audio Rendering Runner

Copilot Instructions:
- Follow Phase 00–05 runner.py EXACTLY.
- Do NOT add logic.
"""

from .input_schema import Phase06Input
from .processor import process
from .debug import write_debug_artifacts

def run(context: dict, input_artifact: dict) -> dict:
    input_model = Phase06Input(**input_artifact)
    output_model = process(input_model)
    write_debug_artifacts(context, output_model)
    return output_model.dict()
