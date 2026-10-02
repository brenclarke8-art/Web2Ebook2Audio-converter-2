"""
Phase 02 — Text Normalization Runner

Copilot Instructions:
- Follow Phase 00 and Phase 01 runner.py EXACTLY.
- Do NOT add logic.
"""

from .input_schema import Phase02Input
from .processor import process
from .debug import write_debug_artifacts

def run(context: dict, input_artifact: dict) -> dict:
    input_model = Phase02Input(**input_artifact)
    output_model = process(input_model)
    write_debug_artifacts(context, output_model)
    return output_model.dict()
