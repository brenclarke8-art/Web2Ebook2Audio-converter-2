# ebook_app/phases/phase1_project.py
"""Phase 1 — Project Setup.

Validates and persists the project configuration: title, author,
source (URL or file path), output directory, and language settings.
No text processing is done in this phase.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ebook_app.phases.phase_base import PhaseBase, PhaseResult

logger = logging.getLogger(__name__)


class Phase1Project(PhaseBase):
    """Phase 1: create or load the project and validate configuration."""

    def run(self, chapter_id: str = "", **kwargs) -> PhaseResult:  # noqa: D401
        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        title = kwargs.get("title", "")
        author = kwargs.get("author", "")
        source = kwargs.get("source", "")
        output_dir = kwargs.get("output_dir", "")

        errors = []
        if not title.strip():
            errors.append("Book title is required.")
        if not source.strip():
            errors.append("A source URL or file path is required.")

        if errors:
            return PhaseResult.error_result("\n".join(errors))

        self._emit_progress(50)

        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        self._emit_progress(100)

        summary_lines = [
            f"Title:  {title}",
            f"Author: {author or '(not set)'}",
            f"Source: {source}",
            f"Output: {output_dir or '(default)'}",
        ]

        return PhaseResult(
            success=True,
            output_text="\n".join(summary_lines),
            data={
                "title": title,
                "author": author,
                "source": source,
                "output_dir": output_dir,
            },
        )
