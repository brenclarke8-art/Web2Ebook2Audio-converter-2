import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Full Kokoro 1.0 voice catalog.
# Keys are the voice IDs used in the API.
# Prefix convention: a=American, b=British; f=female, m=male.
KOKORO_VOICE_CATALOG: Dict[str, Dict[str, str]] = {
    # American English — Female
    "af_heart": {"lang": "en-us", "gender": "female", "description": "Warm American English female voice"},
    "af_alloy": {"lang": "en-us", "gender": "female", "description": "Clear American English female voice"},
    "af_aoede": {"lang": "en-us", "gender": "female", "description": "Melodic American English female voice"},
    "af_bella": {"lang": "en-us", "gender": "female", "description": "Lively American English female voice"},
    "af_jessica": {"lang": "en-us", "gender": "female", "description": "Friendly American English female voice"},
    "af_kore": {"lang": "en-us", "gender": "female", "description": "Crisp American English female voice"},
    "af_nicole": {"lang": "en-us", "gender": "female", "description": "Smooth American English female voice"},
    "af_nova": {"lang": "en-us", "gender": "female", "description": "Dynamic American English female voice"},
    "af_river": {"lang": "en-us", "gender": "female", "description": "Flowing American English female voice"},
    "af_sarah": {"lang": "en-us", "gender": "female", "description": "Natural American English female voice"},
    "af_sky": {"lang": "en-us", "gender": "female", "description": "Light American English female voice"},
    # American English — Male
    "am_adam": {"lang": "en-us", "gender": "male", "description": "Rich American English male voice"},
    "am_echo": {"lang": "en-us", "gender": "male", "description": "Resonant American English male voice"},
    "am_eric": {"lang": "en-us", "gender": "male", "description": "Steady American English male voice"},
    "am_fenrir": {"lang": "en-us", "gender": "male", "description": "Bold American English male voice"},
    "am_liam": {"lang": "en-us", "gender": "male", "description": "Casual American English male voice"},
    "am_michael": {"lang": "en-us", "gender": "male", "description": "Professional American English male voice"},
    "am_onyx": {"lang": "en-us", "gender": "male", "description": "Deep American English male voice"},
    "am_puck": {"lang": "en-us", "gender": "male", "description": "Playful American English male voice"},
    "am_santa": {"lang": "en-us", "gender": "male", "description": "Jolly American English male voice"},
    # British English — Female
    "bf_alice": {"lang": "en-gb", "gender": "female", "description": "Polished British English female voice"},
    "bf_emma": {"lang": "en-gb", "gender": "female", "description": "Clear British English female voice"},
    "bf_isabella": {"lang": "en-gb", "gender": "female", "description": "Elegant British English female voice"},
    "bf_lily": {"lang": "en-gb", "gender": "female", "description": "Soft British English female voice"},
    # British English — Male
    "bm_daniel": {"lang": "en-gb", "gender": "male", "description": "Distinguished British English male voice"},
    "bm_fable": {"lang": "en-gb", "gender": "male", "description": "Storytelling British English male voice"},
    "bm_george": {"lang": "en-gb", "gender": "male", "description": "Authoritative British English male voice"},
    "bm_lewis": {"lang": "en-gb", "gender": "male", "description": "Warm British English male voice"},
}

# Ordered list for UI display (voices grouped by language/gender)
KOKORO_VOICE_LIST = list(KOKORO_VOICE_CATALOG.keys())


def get_lang_for_voice(voice: str) -> str:
    """Return the BCP-47 language tag for a given voice ID."""
    entry = KOKORO_VOICE_CATALOG.get(voice)
    if entry:
        return entry["lang"]
    # Infer from prefix: af_/am_ → en-us, bf_/bm_ → en-gb
    if voice.startswith(("af_", "am_")):
        return "en-us"
    if voice.startswith(("bf_", "bm_")):
        return "en-gb"
    return "en-us"
