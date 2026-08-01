"""Tests for phases/phase_base.py cancel/reset/progress infrastructure."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from ebook_app.phases.phase_base import PhaseBase, PhaseResult


# ─────────────────────────────────────────────────────────────────────────────
# Concrete implementation for testing
# ─────────────────────────────────────────────────────────────────────────────

class _AlwaysSuccessPhase(PhaseBase):
    def run(self, chapter_id: str, **kwargs: Any) -> PhaseResult:
        if self.is_cancelled():
            return PhaseResult(success=False, cancelled=True)
        return PhaseResult(success=True, output_text="done")


class _CancellablePhase(PhaseBase):
    """Phase that checks cancel flag in a loop."""

    def run(self, chapter_id: str, **kwargs: Any) -> PhaseResult:
        for _ in range(100):
            if self.is_cancelled():
                return PhaseResult(success=False, cancelled=True, output_text="cancelled")
            self._emit_progress(1)
        return PhaseResult(success=True, output_text="finished")


class _FailingPhase(PhaseBase):
    def run(self, chapter_id: str, **kwargs: Any) -> PhaseResult:
        return PhaseResult(success=False, error="Something went wrong")


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_phase_runs_successfully():
    phase = _AlwaysSuccessPhase(settings={})
    result = phase.run("ch1")
    assert result.success is True
    assert result.cancelled is False


def test_cancel_before_run():
    phase = _CancellablePhase(settings={})
    phase.cancel()
    assert phase.is_cancelled() is True
    result = phase.run("ch1")
    assert result.cancelled is True
    assert result.success is False


def test_cancel_during_run_loop():
    """Cancel flag mid-execution stops the loop."""
    phase = _CancellablePhase(settings={})

    call_count = 0

    def progress_cb(pct):
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            phase.cancel()

    phase.set_progress_callback(progress_cb)
    result = phase.run("ch1")
    assert result.cancelled is True
    assert call_count >= 3


def test_reset_clears_cancel_flag():
    phase = _AlwaysSuccessPhase(settings={})
    phase.cancel()
    assert phase.is_cancelled() is True
    phase.reset()
    assert phase.is_cancelled() is False


def test_reset_allows_run_after_cancel():
    phase = _AlwaysSuccessPhase(settings={})
    phase.cancel()
    phase.reset()
    result = phase.run("ch1")
    assert result.success is True
    assert result.cancelled is False


def test_progress_callback_called():
    phase = _CancellablePhase(settings={})
    received = []
    phase.set_progress_callback(received.append)
    result = phase.run("ch1")
    assert result.success is True
    assert len(received) > 0


def test_phase_result_defaults():
    r = PhaseResult(success=True)
    assert r.output_text == ""
    assert r.data == {}
    assert r.cancelled is False
    assert r.error == ""


def test_failing_phase_returns_error():
    phase = _FailingPhase(settings={})
    result = phase.run("ch1")
    assert result.success is False
    assert result.error == "Something went wrong"
    assert result.cancelled is False
