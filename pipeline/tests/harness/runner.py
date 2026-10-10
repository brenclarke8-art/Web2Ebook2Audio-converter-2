from .logger import write_log


def run_phase(phase_runner, context, input_artifact, log_name):
    try:
        output_artifact = phase_runner(context, input_artifact)
    except Exception as exc:
        write_log(log_name, input_artifact, {"error": str(exc)})
        raise
    write_log(log_name, input_artifact, output_artifact)
    return output_artifact
