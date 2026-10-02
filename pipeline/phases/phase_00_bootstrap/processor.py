import time
from .input_schema import Phase00Input
from .output_schema import Phase00Output

def process(input_data: Phase00Input) -> Phase00Output:
    """
    Pure logic for Phase 00 — Bootstrap & Config Validation.
    No filesystem access. No logging. Deterministic output.
    """

    start_time = time.time()

    # Normalize settings and environment
    normalized = {
        "config_version": input_data.settings.get("version", "unknown"),
        "env_mode": input_data.env.get("MODE", "development"),
        "raw_settings": input_data.settings,
        "raw_env": input_data.env,
    }

    # Readiness checks (expand later)
    readiness = {
        "settings_loaded": bool(input_data.settings),
        "env_loaded": bool(input_data.env),
        "dependencies_ok": True,  # placeholder for real dependency checks
    }

    # Build output model
    output = Phase00Output(
        normalized_config=normalized,
        readiness_report=readiness,

        meta={
            "phase": "00_bootstrap",
            "version": "1.0.0",
            "timestamp": time.time(),
        },

        input_summary={
            "settings_keys": list(input_data.settings.keys()),
            "env_keys": list(input_data.env.keys()),
        },

        output_summary={
            "config_version": normalized["config_version"],
            "env_mode": normalized["env_mode"],
        },

        errors=[],
        warnings=[],
        timings={"total_ms": (time.time() - start_time) * 1000},
    )

    return output
