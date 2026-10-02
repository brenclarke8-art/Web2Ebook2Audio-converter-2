import json
from pathlib import Path
from .input_schema import Phase00Input
from .processor import process
from .debug import write_debug_artifacts

def run(context: dict, input_artifact: dict) -> dict:
    """
    Universal runner contract for all phases:
    run(context, input_artifact) -> output_artifact (dict)

    Responsibilities:
    - Validate input schema
    - Execute processor
    - Write debug artifacts
    - Return output as a dict
    """

    # Validate input schema
    input_model = Phase00Input(**input_artifact)

    # Execute processor
    output_model = process(input_model)

    # Write debug artifacts
    write_debug_artifacts(context, output_model)

    # Return output as dict
    return output_model.dict()
