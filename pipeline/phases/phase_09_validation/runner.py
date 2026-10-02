"""
Phase 09 — File Writing & Export Runner

Copilot Instructions:
- Follow Phase 00–08 runner.py EXACTLY.
- Do NOT add logic.
"""

from .input_schema import Phase09Input
from .processor import process
from .debug import write_debug_artifacts

def run(context: dict, input_artifact: dict) -> dict:
    input_model = Phase09Input(**input_artifact)
    output_model = process(input_model, context)
    write_debug_artifacts(context, output_model)
    return output_model.dict()
