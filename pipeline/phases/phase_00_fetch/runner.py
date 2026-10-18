from .input_schema import Phase00FetchInput
from .processor import process
from .debug import write_debug_artifacts
from .infer_rules import save_learned_rule

def run(context: dict, input_artifact: dict) -> dict:
    input_model = Phase00FetchInput(**input_artifact)
    output_model = process(input_model)

    learned = output_model.meta.get("learned_rule")
    if isinstance(learned, dict):
        domain = learned.get("domain")
        rule = learned.get("rule")
        if isinstance(domain, str) and isinstance(rule, dict):
            save_learned_rule(domain, rule)

    # Pass full context to debug writer
    write_debug_artifacts(context, output_model)

    return output_model.model_dump()
