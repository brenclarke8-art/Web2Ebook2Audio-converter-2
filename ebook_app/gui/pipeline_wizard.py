# ebook_app/gui/pipeline_wizard.py
"""Pipeline Wizard — the central UI component that guides the user through
all 8 phases of the pipeline for one or more chapters.

Layout
──────
  Top:    StepProgressBar (phase 1-8 status indicators)
  Center: QStackedWidget — one panel per phase + chapter gate screen
  Bottom: log console dock is managed by MainWindow

Mode-based flow
───────────────
  manual    → run phase → show output → wait for "Confirm & Continue"
  semi_auto → auto-run phases 1-5b → pause at phase 6 → auto-run 7-8
              between chapters: pause at chapter gate
  auto      → run all phases for all chapters without pausing
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ebook_app.gui.phase_panels._base_panel import BasePhasePanel
from ebook_app.gui.phase_panels.phase1_panel import Phase1Panel
from ebook_app.gui.phase_panels.phase2_panel import Phase2Panel
from ebook_app.gui.phase_panels.phase3_panel import Phase3Panel
from ebook_app.gui.phase_panels.phase4_panel import Phase4Panel
from ebook_app.gui.phase_panels.phase5a_panel import Phase5aPanel
from ebook_app.gui.phase_panels.phase5b_panel import Phase5bPanel
from ebook_app.gui.phase_panels.phase6_panel import Phase6Panel
from ebook_app.gui.phase_panels.phase7_panel import Phase7Panel
from ebook_app.gui.phase_panels.phase8_panel import Phase8Panel
from ebook_app.gui.phase_panels.chapter_gate_panel import ChapterGatePanel

logger = logging.getLogger(__name__)

# Phase panel index constants
_IDX_P1 = 0
_IDX_P2 = 1
_IDX_P3 = 2
_IDX_P4 = 3
_IDX_P5A = 4
_IDX_P5B = 5
_IDX_P6 = 6
_IDX_P7 = 7
_IDX_P8 = 8
_IDX_GATE = 9   # chapter gate screen

_STATE_LOCKED = "locked"
_STATE_ACTIVE = "active"
_STATE_DONE = "done"
_STATE_FAILED = "failed"

_STEP_LABELS = [
    "1. Project",
    "2. Retrieval",
    "3. Translation",
    "4. Segmentation",
    "5a. Characters",
    "5b. Classification",
    "6. Review",
    "7. Audio",
    "8. Output",
]

_ICONS = {
    _STATE_LOCKED: "🔒",
    _STATE_ACTIVE: "⏳",
    _STATE_DONE: "✅",
    _STATE_FAILED: "❌",
}


# ---------------------------------------------------------------------------
# Step progress bar
# ---------------------------------------------------------------------------

class StepProgressBar(QWidget):
    step_clicked = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        for i, label in enumerate(_STEP_LABELS):
            btn = QPushButton(f"🔒 {label}")
            btn.setCheckable(False)
            btn.setEnabled(False)
            btn.setMinimumWidth(80)
            btn.setFixedHeight(30)
            btn.setStyleSheet("font-size: 10px; padding: 2px 4px;")
            idx = i
            btn.clicked.connect(lambda checked=False, x=idx: self.step_clicked.emit(x))
            self._buttons.append(btn)
            layout.addWidget(btn)

    def set_state(self, phase_idx: int, state: str) -> None:
        if 0 <= phase_idx < len(self._buttons):
            btn = self._buttons[phase_idx]
            icon = _ICONS.get(state, "🔒")
            label = _STEP_LABELS[phase_idx]
            btn.setText(f"{icon} {label}")
            btn.setEnabled(state == _STATE_DONE)


# ---------------------------------------------------------------------------
# Phase runner QThread
# ---------------------------------------------------------------------------

class _PhaseRunnerThread(QThread):
    """Runs a phase controller's run() in a background thread."""

    finished = Signal(object)   # PhaseResult
    progress = Signal(int)

    def __init__(self, phase_controller: Any, chapter_id: str, kwargs: dict, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = phase_controller
        self._chapter_id = chapter_id
        self._kwargs = kwargs

    def run(self) -> None:
        self._ctrl.set_progress_callback(self.progress.emit)
        result = self._ctrl.run(self._chapter_id, **self._kwargs)
        self.finished.emit(result)


# ---------------------------------------------------------------------------
# Pipeline Wizard
# ---------------------------------------------------------------------------

class PipelineWizard(QWidget):
    """Main pipeline wizard widget.

    Signals
    -------
    pipeline_cancelled
        Emitted when the user confirms cancellation.
    pipeline_complete
        Emitted when all selected chapters have been fully processed.
    log_message
        ``(message, level)`` emitted for log console forwarding.
    """

    pipeline_cancelled = Signal()
    pipeline_complete = Signal()
    log_message = Signal(str, str)

    def __init__(self, settings: Any, project_manager: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.project_manager = project_manager

        self._cancel_requested: bool = False
        self._current_phase_idx: int = 0
        self._phase_states: List[str] = [_STATE_LOCKED] * 9
        self._phase_data: Dict[str, Any] = {}   # accumulated data between phases

        # Active runners
        self._runner: Optional[_PhaseRunnerThread] = None
        self._chapter_iterator = None
        self._phase_controllers: Dict[str, Any] = {}

        self._build_ui()
        self._build_phase_controllers()

    # ─────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Step progress bar
        self._step_bar = StepProgressBar()
        outer.addWidget(self._step_bar)

        # Stacked phase panels
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer.addWidget(self._stack, 1)

        # Build panels
        self._panels: List[BasePhasePanel] = []
        panel_classes = [
            Phase1Panel, Phase2Panel, Phase3Panel, Phase4Panel,
            Phase5aPanel, Phase5bPanel, Phase6Panel, Phase7Panel, Phase8Panel,
        ]
        for cls in panel_classes:
            panel = cls(self.settings)
            panel.run_requested.connect(self._on_run_requested)
            panel.cancel_requested.connect(self._on_cancel_requested)
            panel.back_requested.connect(self._on_back_requested)
            self._panels.append(panel)
            self._stack.addWidget(panel)

        # Chapter gate screen
        self._gate_panel = ChapterGatePanel()
        self._gate_panel.next_requested.connect(self._on_chapter_gate_next)
        self._gate_panel.cancel_requested.connect(self._on_cancel_requested)
        self._stack.addWidget(self._gate_panel)

        # Activate first panel
        self._set_phase(0)

    # ─────────────────────────────────────────────────────────────────────
    # Phase controllers
    # ─────────────────────────────────────────────────────────────────────

    def _build_phase_controllers(self) -> None:
        from ebook_app.phases.phase1_project import Phase1Project
        from ebook_app.phases.phase2_retrieval import Phase2Retrieval
        from ebook_app.phases.phase3_translation import Phase3Translation
        from ebook_app.phases.phase4_segmentation import Phase4Segmentation
        from ebook_app.phases.phase5a_characters import Phase5aCharacters
        from ebook_app.phases.phase5b_classification import Phase5bClassification
        from ebook_app.phases.phase6_review_prep import Phase6ReviewPrep
        from ebook_app.phases.phase7_audio import Phase7Audio
        from ebook_app.phases.phase8_output import Phase8Output

        self._phase_controllers = {
            0: Phase1Project(self.settings),
            1: Phase2Retrieval(self.settings),
            2: Phase3Translation(self.settings),
            3: Phase4Segmentation(self.settings),
            4: Phase5aCharacters(self.settings),
            5: Phase5bClassification(self.settings),
            6: Phase6ReviewPrep(self.settings),
            7: Phase7Audio(self.settings),
            8: Phase8Output(self.settings),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Navigation
    # ─────────────────────────────────────────────────────────────────────

    def _set_phase(self, idx: int) -> None:
        self._current_phase_idx = idx
        self._stack.setCurrentIndex(idx)
        if 0 <= idx < 9:
            self._phase_states[idx] = _STATE_ACTIVE
            self._step_bar.set_state(idx, _STATE_ACTIVE)

    def _mark_phase_done(self, idx: int) -> None:
        self._phase_states[idx] = _STATE_DONE
        self._step_bar.set_state(idx, _STATE_DONE)

    def _mark_phase_failed(self, idx: int) -> None:
        self._phase_states[idx] = _STATE_FAILED
        self._step_bar.set_state(idx, _STATE_FAILED)

    # ─────────────────────────────────────────────────────────────────────
    # Run / Cancel / Back
    # ─────────────────────────────────────────────────────────────────────

    @Slot()
    def _on_run_requested(self) -> None:
        idx = self._current_phase_idx
        if idx not in self._phase_controllers:
            return

        ctrl = self._phase_controllers[idx]
        panel = self._panels[idx]
        kwargs = panel.get_phase_kwargs()
        kwargs.update(self._phase_data)   # inject accumulated chapter data

        # Inject project-level objects
        kwargs.setdefault("work_dir", self._get_work_dir())
        kwargs.setdefault("output_dir", self.settings.get("output_dir", "output"))
        kwargs.setdefault("character_db", self._get_character_db())

        panel.set_running(True)
        panel.clear_output()

        chapter_id = self._phase_data.get("chapter_id", "ch1")
        self._runner = _PhaseRunnerThread(ctrl, chapter_id, kwargs)
        self._runner.finished.connect(self._on_phase_finished)
        self._runner.progress.connect(lambda pct, p=panel: p.set_progress(pct) if hasattr(p, "set_progress") else None)
        self._runner.start()

    @Slot(object)
    def _on_phase_finished(self, result: Any) -> None:
        idx = self._current_phase_idx
        panel = self._panels[idx]
        panel.set_running(False)

        if result.cancelled:
            self.log_message.emit(f"Phase {idx + 1} cancelled.", "WARNING")
            self.reset_pipeline()
            return

        if not result.success:
            self.log_message.emit(f"Phase {idx + 1} failed: {result.error}", "ERROR")
            self._mark_phase_failed(idx)
            panel.show_output(f"❌ Failed: {result.error}")
            return

        self.log_message.emit(f"Phase {idx + 1} complete.", "SUCCESS")
        panel.show_output(result.output_text)
        self._mark_phase_done(idx)

        # Merge result data into accumulated phase data
        self._phase_data.update(result.data)

        # Update panel-specific displays
        self._update_panel_after_phase(idx, result)

        mode = self.settings.get("pipeline_mode", "manual")
        self._advance_or_wait(idx, mode)

    def _update_panel_after_phase(self, idx: int, result: Any) -> None:
        panel = self._panels[idx]
        if idx == 3:  # Phase 4 segmentation
            if hasattr(panel, "show_segments"):
                panel.show_segments(result.data.get("segments", []))
        elif idx == 4:  # Phase 5a characters
            if hasattr(panel, "show_characters"):
                panel.show_characters(result.data.get("characters", []))
        elif idx == 5:  # Phase 5b classification
            if hasattr(panel, "show_segments"):
                panel.show_segments(result.data.get("segments", []))
        elif idx == 6:  # Phase 6 review
            if hasattr(panel, "show_segments"):
                panel.show_segments(result.data.get("segments", []))
        elif idx == 7:  # Phase 7 audio
            if hasattr(panel, "set_complete"):
                panel.set_complete(result.data.get("chapter_audio", ""))
        elif idx == 8:  # Phase 8 output
            if hasattr(panel, "show_output_files"):
                panel.show_output_files(
                    result.data.get("epub_path", ""),
                    result.data.get("audio_files", []),
                    result.data.get("output_dir", ""),
                )

    def _advance_or_wait(self, completed_idx: int, mode: str) -> None:
        """Decide whether to advance automatically or wait for user confirmation."""
        next_idx = completed_idx + 1

        if next_idx > 8:
            # All phases done — pipeline complete for this chapter
            self.log_message.emit("All phases complete for this chapter.", "SUCCESS")
            self.pipeline_complete.emit()
            return

        pause_phases = set()
        if mode == "manual":
            pause_phases = set(range(9))   # pause after every phase
        elif mode == "semi_auto":
            pause_phases = {6}  # pause only at phase 6 (review)

        if completed_idx in pause_phases:
            # Stay on current panel in confirm mode; user clicks to advance
            panel = self._panels[completed_idx]
            panel.set_confirm_mode(True)
            panel.run_requested.disconnect()
            panel.run_requested.connect(lambda idx=next_idx: self._set_phase(idx))
        else:
            # Auto-advance to next phase
            self._set_phase(next_idx)
            if mode == "auto":
                self._on_run_requested()

    @Slot()
    def _on_cancel_requested(self) -> None:
        self._cancel_requested = True
        ctrl = self._phase_controllers.get(self._current_phase_idx)
        if ctrl:
            ctrl.cancel()
        if self._chapter_iterator:
            self._chapter_iterator.cancel()

    @Slot()
    def _on_back_requested(self) -> None:
        if self._current_phase_idx > 0:
            self._set_phase(self._current_phase_idx - 1)

    # ─────────────────────────────────────────────────────────────────────
    # Chapter gate
    # ─────────────────────────────────────────────────────────────────────

    def show_chapter_gate(self, completed_num: int, next_num: int, total: int) -> None:
        self._gate_panel.update_info(completed_num, next_num, total)
        self._stack.setCurrentIndex(_IDX_GATE)

    @Slot()
    def _on_chapter_gate_next(self) -> None:
        self.reset_pipeline(keep_project=True)

    # ─────────────────────────────────────────────────────────────────────
    # Reset
    # ─────────────────────────────────────────────────────────────────────

    def reset_pipeline(self, *, keep_project: bool = False) -> None:
        """Reset wizard to Phase 1, clear all transient state."""
        self._cancel_requested = False

        # Reset all phase controllers
        for ctrl in self._phase_controllers.values():
            ctrl.reset()

        # Reset UI state
        for i in range(9):
            self._phase_states[i] = _STATE_LOCKED
            self._step_bar.set_state(i, _STATE_LOCKED)
            self._panels[i].clear_output()
            self._panels[i].set_running(False)

        # Reconnect run buttons (may have been rewired for confirm mode)
        for panel in self._panels:
            try:
                panel.run_requested.disconnect()
            except Exception:
                pass
            panel.run_requested.connect(self._on_run_requested)

        if not keep_project:
            self._phase_data = {}
        self._set_phase(0)
        self.pipeline_cancelled.emit()

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _get_work_dir(self):
        if self.project_manager:
            return self.project_manager.get_work_dir()
        return None

    def _get_character_db(self):
        if self.project_manager:
            from ebook_app.core.character_db import CharacterDatabase
            work_dir = self.project_manager.get_work_dir()
            if work_dir:
                return CharacterDatabase(path=work_dir / "character_database.json")
        return None

    def set_chapter_id(self, chapter_id: str) -> None:
        self._phase_data["chapter_id"] = chapter_id

    def inject_phase_data(self, data: dict) -> None:
        """Inject external data (e.g. source URL) into the accumulated phase data."""
        self._phase_data.update(data)
