Phase 06 — Voice Assignment
Responsibility
Own voice mapping and TTS preparation.
Convert semantic character attribution into TTS-ready voice assignments.
Map narrator and character identities to voice definitions.
Support both manual and adaptive voice assignment modes.
Inputs
enriched_segments
character_registry
settings
Outputs
voice_registry[]

Fields:

voice_id
character_id
voice_role (narrator | character | fallback)
provider
voice_name
generation_settings
voice_segments[]

Fields:

segment_id
voice_id
character_id
voice_role
primary_type
Additional Outputs
voice_registry
voice_segments
meta
input_summary
output_summary
errors
warnings
timings
Rules
Perform voice assignment only.
Do NOT perform character discovery.
Do NOT perform speaker attribution.
Do NOT perform narration/dialogue/thought classification.
Do NOT perform semantic analysis.
Do NOT modify enriched_segments semantic decisions.

All character references must use canonical:

character_id


values from the character registry.

Voice assignment must operate using:

speaker_id
thought_owner_id
character_id


and never raw character names.

Voice Modes
Manual Mode
settings.tts.voice_mode = "manual"


Behavior:

Use user-defined character-to-voice mappings.
Maintain fixed voice assignments.
No AI-driven voice optimization.
Preserve consistent speaker identities throughout the book.

Example:

Narrator -> Aria
Sarah -> Jenny
John -> Guy

Adaptive Mode
settings.tts.voice_mode = "adaptive"


Behavior:

Use character_profile information when available.
Use emotion_tag information when available.
Allow future intelligent voice matching.
Allow future provider-specific voice optimization.

The output schema must remain identical to Manual Mode.

Only assignment logic may differ.

Voice Registry Example
{
    "voice_id": "voice_char_001",
    "character_id": "char_001",
    "voice_role": "character",
    "provider": "edge",
    "voice_name": "en-US-AriaNeural",
    "generation_settings": {
        "style": "neutral",
        "pitch": 0,
        "speed": 1.0
    }
}

Voice Segment Example
{
    "segment_id": "ch1_seg0007",
    "voice_id": "voice_char_001",
    "character_id": "char_001",
    "voice_role": "character",
    "primary_type": "dialogue"
}

Future TODOs
Add adaptive voice-selection strategies.
Add emotion-aware TTS rendering.
Add provider-specific voice optimization.
Add multi-provider voice fallback support.
Add voice consistency validation across books and series.
Add automatic narrator voice profiling.
Add support for dynamic speaking styles, pacing, and emphasis controls.