# ebook_app/pipeline/phases.py
"""
Canonical pipeline step list for the entire application.

This file defines the exact order of execution for the 7‑phase hybrid pipeline.
The UI, controller, and tests all reference this list.

Each entry corresponds to a method name on PipelineController.
"""

PIPELINE_STEPS = [
    "scrape_index",          # Phase 1
    "scrape_chapters",       # Phase 2
    "pass1_extraction",      # Phase 3
    "pass2_classification",  # Phase 4
    "smart_review_dialogue", # Phase 5
    "tts_generate",          # Phase 6
    "epub_build",            # Phase 7
]
