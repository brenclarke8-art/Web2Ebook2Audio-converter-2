# ebook_app/phases/phase_base.py
"""Shared base class for all pipeline phase controllers.

Every phase controller inherits from PhaseBase which provides:
  - cancel() / reset() / is_cancelled()
  - progress callback wiring
  - a standard PhaseResult return type
  - an abstract run() method
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class PhaseResult:
    """Standard result object returned by every phase's run() method."""

    success: bool = True
    """True when the phase completed without error."""

    output_text: str = ""
    """Human-readable summary / preview of the phase output (shown in the UI diff panel)."""

    data: Dict[str, Any] = field(default_factory=dict)
    """Structured output data that subsequent phases can consume."""

    cancelled: bool = False
    """True when the phase was stopped by the user before completion."""

    error: str = ""
    """Error message when success is False."""

    @classmethod
    def cancelled_result(cls) -> "PhaseResult":
        return cls(success=False, cancelled=True, error="Cancelled by user.")

    @classmethod
    def error_result(cls, message: str) -> "PhaseResult":
        return cls(success=False, error=message)


class PhaseBase(ABC):
    """Abstract base for all pipeline phases.

    Usage::

        class Phase2Retrieval(PhaseBase):
            def run(self, chapter_id: str, **kwargs) -> PhaseResult:
                if self.is_cancelled():
                    return PhaseResult.cancelled_result()
                ...
                self._emit_progress(50)
                ...
                return PhaseResult(success=True, output_text="Cleaned text", data={...})
    """

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._cancelled: bool = False
        self._progress_callback: Optional[Callable[[int], None]] = None

    # ─────────────────────────────────────────────────────────────────────
    # Cancellation
    # ─────────────────────────────────────────────────────────────────────

    def cancel(self) -> None:
        """Signal this phase to stop at the next safe checkpoint."""
        logger.debug("[%s] Cancel requested.", self.__class__.__name__)
        self._cancelled = True

    def reset(self) -> None:
        """Clear cancellation flag and any transient in-progress state."""
        logger.debug("[%s] Reset.", self.__class__.__name__)
        self._cancelled = False
        self._on_reset()

    def is_cancelled(self) -> bool:
        """Return True if cancel() has been called since the last reset()."""
        return self._cancelled

    # ─────────────────────────────────────────────────────────────────────
    # Progress reporting
    # ─────────────────────────────────────────────────────────────────────

    def set_progress_callback(self, cb: Callable[[int], None]) -> None:
        """Register a callback(percent: int) that is called during run()."""
        self._progress_callback = cb

    def _emit_progress(self, percent: int) -> None:
        """Emit a progress update (0–100) to the registered callback."""
        if self._progress_callback:
            try:
                self._progress_callback(max(0, min(100, percent)))
            except Exception:
                logger.debug(
                    "[%s] Progress callback raised an exception.",
                    self.__class__.__name__,
                    exc_info=True,
                )

    # ─────────────────────────────────────────────────────────────────────
    # Extension hooks
    # ─────────────────────────────────────────────────────────────────────

    def _on_reset(self) -> None:
        """Override in subclass to clear phase-specific in-progress state."""

    # ─────────────────────────────────────────────────────────────────────
    # Abstract interface
    # ─────────────────────────────────────────────────────────────────────

    @abstractmethod
    def run(self, chapter_id: str, **kwargs) -> PhaseResult:
        """Execute the phase for *chapter_id* and return a PhaseResult.

        Implementations should check ``self.is_cancelled()`` frequently and
        return ``PhaseResult.cancelled_result()`` if it is True.
        """
