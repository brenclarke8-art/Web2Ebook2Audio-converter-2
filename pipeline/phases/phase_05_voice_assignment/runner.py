"""
Phase 05 — Audio Script Generation Runner

Copilot Instructions:
- Follow Phase 00–04 runner.py EXACTLY.
- Do NOT add logic.
"""

from .input_schema import Phase05Input
from .processor import process
from .debug import write_debug_artifacts

def run(context: dict, input_artifact: dict) -> dict:
    input_model = Phase05Input(**input_artifact)
    output_model = process(input_model)
    write_debug_artifacts(context, output_model)
    return output_model.dict()
