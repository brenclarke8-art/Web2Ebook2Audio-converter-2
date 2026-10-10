from .input_schema import Phase00FetchInput
from .processor import process
from .debug import write_debug_artifacts

def run(context: dict, input_artifact: dict) -> dict:
    input_model = Phase00FetchInput(**input_artifact)
    output_model = process(input_model)

    # Pass full context to debug writer
    write_debug_artifacts(context, output_model)

    return output_model.model_dump()
