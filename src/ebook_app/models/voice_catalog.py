import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Minimal example; extend with your full catalog as needed.
KOKORO_VOICE_CATALOG: Dict[str, Dict[str, str]] = {
    "af_heart": {
        "gender": "female",
        "description": "Warm American English female voice",
    },
    "am_mellow": {
        "gender": "male",
        "description": "Calm American English male voice",
    },
    # Add the rest of your voices here...
}