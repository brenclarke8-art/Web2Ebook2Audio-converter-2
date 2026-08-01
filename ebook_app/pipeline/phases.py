# ebook_app/pipeline/phases.py
"""
Canonical pipeline phase list for the entire application.

This file defines the exact order of execution for the 8-phase pipeline.
The UI, controller, and tests all reference this list.

Each entry is both a human-readable label used in the GUI and a key used
to look up the corresponding phase controller in ``phases/``.
"""

PIPELINE_PHASES = [
    "phase1_project",        # Phase 1  — Project creation & configuration
    "phase2_retrieval",      # Phase 2  — Text retrieval/input & cleaning
    "phase3_translation",    # Phase 3  — Optional translation
    "phase4_segmentation",   # Phase 4  — Text segmentation
    "phase5a_characters",    # Phase 5a — Character identification & storage
    "phase5b_classification",# Phase 5b — LLM classification (type/speaker/gender/confidence)
    "phase6_review_prep",    # Phase 6  — Review & audio generation prep
    "phase7_audio",          # Phase 7  — Audio generation
    "phase8_output",         # Phase 8  — Output (EPUB + audio export)
]

PHASE_LABELS = {
    "phase1_project":         "1. Project Setup",
    "phase2_retrieval":       "2. Text Retrieval",
    "phase3_translation":     "3. Translation",
    "phase4_segmentation":    "4. Segmentation",
    "phase5a_characters":     "5a. Characters",
    "phase5b_classification": "5b. LLM Classification",
    "phase6_review_prep":     "6. Review & Prep",
    "phase7_audio":           "7. Audio Generation",
    "phase8_output":          "8. Output",
}

# Backward-compat alias used by older tests / pipeline controller code.
PIPELINE_STEPS = PIPELINE_PHASES

