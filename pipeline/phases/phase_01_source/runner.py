"""
Phase 01 — Source Acquisition Runner

Copilot Instructions:
- Follow Phase 00 runner.py EXACTLY.
- Do NOT add additional logic.
- Do NOT modify processor behavior.
- Do NOT perform filesystem writes here (debug.py handles artifacts).
- This file defines the universal pipeline contract:
    run(context, input_artifact) -> output_artifact (dict)
- runner.py must ONLY call process() and write debug artifacts.
- Do NOT inspect or modify chapter_range here. Only processor.py handles chapter filtering.
"""

from .input_schema import Phase01Input
from .processor import process
from .debug import write_debug_artifacts

def run(context: dict, input_artifact: dict) -> dict:
    input_model = Phase01Input(**input_artifact)
    output_model = process(input_model)
    write_debug_artifacts(context, output_model)
    return output_model.dict()
