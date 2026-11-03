"""
Phase 10 — File Writing & Export Runner

Copilot Instructions:
- Follow Phase 00–08 runner.py EXACTLY.
- Do NOT add logic.
"""

from .input_schema import Phase10Input
from .processor import process
from .debug import write_debug_artifacts

def run(context: dict, input_artifact: dict) -> dict:
    input_model = Phase10Input(**input_artifact)
    output_model = process(input_model)
    write_debug_artifacts(context, output_model)
    return output_model.dict()
