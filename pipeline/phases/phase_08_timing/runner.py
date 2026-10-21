"""
Phase 07 — Audio Stitching Runner

Copilot Instructions:
- Follow Phase 00–06 runner.py EXACTLY.
- Do NOT add logic.
"""

from .input_schema import Phase07Input
from .processor import process
from .debug import write_debug_artifacts

def run(context: dict, input_artifact: dict) -> dict:
    input_model = Phase07Input(**input_artifact)
    output_model = process(input_model)
    write_debug_artifacts(context, output_model)
    return output_model.dict()
