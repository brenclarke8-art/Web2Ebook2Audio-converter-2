# src/ebook_app/ui/pages/chapter_preview_page.py
"""Chapter Preview page — browse and reprocess chapters."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QMessageBox,
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from ebook_app.ui.pages._base_page import BasePage
from ebook_app.ui.dialogs.epub_chapter_preview_dialog import (
    EpubChapterPreviewDialog,
)


class ChapterPreviewPage(BasePage):
    """Page for previewing and reprocessing chapters.

    Left panel: chapter list.
    Right panel: chapter text viewer + reprocessing actions.
    """

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- Chapter list --
        list_container = QGroupBox("Chapters")
        list_vbox = QVBoxLayout(list_container)
        self._chapter_list = QListWidget()
        self._chapter_list.currentRowChanged.connect(self._on_chapter_selected)
        list_vbox.addWidget(self._chapter_list)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh)
        list_vbox.addWidget(refresh_btn)

        splitter.addWidget(list_container)

        # -- Chapter viewer --
        viewer_container = QGroupBox("Content")
        viewer_vbox = QVBoxLayout(viewer_container)

        self._chapter_label = QLabel("Select a chapter to preview")
        viewer_vbox.addWidget(self._chapter_label)

        # Action buttons row
        btn_row = QHBoxLayout()
        self._btn_reclean = QPushButton("Re-clean Chapter")
        self._btn_reclean.clicked.connect(self._on_reclean)
        btn_row.addWidget(self._btn_reclean)

        self._btn_resemantic = QPushButton("Re-run Semantic Analysis")
        self._btn_resemantic.clicked.connect(self._on_resemantic)
        btn_row.addWidget(self._btn_resemantic)

        self._btn_audio_preview = QPushButton("Preview Audio")
        self._btn_audio_preview.clicked.connect(self._on_audio_preview)
        btn_row.addWidget(self._btn_audio_preview)

        viewer_vbox.addLayout(btn_row)

        self._text_view = QTextEdit()
        self._text_view.setReadOnly(True)
        viewer_vbox.addWidget(self._text_view)

        # Audio preview player
        self._audio_output = QAudioOutput()
        self._audio_player = QMediaPlayer()
        self._audio_player.setAudioOutput(self._audio_output)

        audio_controls = QHBoxLayout()
        self._btn_play = QPushButton("▶ Play")
        self._btn_pause = QPushButton("⏸ Pause")
        self._btn_stop = QPushButton("■ Stop")

        self._btn_play.clicked.connect(self._on_audio_play)
        self._btn_pause.clicked.connect(self._on_audio_pause)
        self._btn_stop.clicked.connect(self._on_audio_stop)

        audio_controls.addWidget(self._btn_play)
        audio_controls.addWidget(self._btn_pause)
        audio_controls.addWidget(self._btn_stop)

        viewer_vbox.addLayout(audio_controls)

        splitter.addWidget(viewer_container)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        self._layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_refresh(self) -> None:
        """Load chapter list from project manager."""
        if not self.project_manager:
            self.log.log("No project loaded.", level="WARNING")
            return

        chapters = self.project_manager.get_chapters() or []
        self._chapter_list.clear()

        for i, ch in enumerate(chapters):
            title = ch.get("title") or f"Chapter {i+1}"
            self._chapter_list.addItem(f"{i+1}. {title}")

        self.log.log("Chapter list refreshed.", level="INFO")

    def _on_chapter_selected(self, index: int) -> None:
        """Load cleaned/semantic text for the selected chapter."""
        if index < 0 or not self.project_manager:
            return

        work_dir = self.project_manager.get_work_dir()
        chapter_id = f"ch{index:03d}"

        # cleaned_final
        cleaned_final = work_dir / f"{chapter_id}_cleaned_final.txt"
        if cleaned_final.exists():
            self._chapter_label.setText(f"Chapter {index+1} (cleaned_final)")
            self._text_view.setPlainText(cleaned_final.read_text(encoding="utf-8"))
            return

        # cleaned
        cleaned = work_dir / f"{chapter_id}_cleaned.txt"
        if cleaned.exists():
            self._chapter_label.setText(f"Chapter {index+1} (cleaned)")
            self._text_view.setPlainText(cleaned.read_text(encoding="utf-8"))
            return

        # semantic segments
        info_file = work_dir / chapter_id / "chapter_info.json"
        if info_file.exists():
            try:
                import json
                data = json.loads(info_file.read_text(encoding="utf-8"))
                segments = data.get("segments", [])
                lines = []
                for seg in segments:
                    text = seg.get("text", "").strip()
                    if not text:
                        continue
                    if seg.get("type") == "narration":
                        lines.append(text)
                    else:
                        speaker = seg.get("speaker", "narrator").upper()
                        lines.append(f"[{speaker}] {text}")
                self._chapter_label.setText(f"Chapter {index+1} (semantic)")
                self._text_view.setPlainText("\n\n".join(lines))
                return
            except Exception:
                pass

        # fallback: raw
        chapters = self.project_manager.get_chapters() or []
        if index < len(chapters):
            raw = chapters[index].get("content", "")
            self._chapter_label.setText(f"Chapter {index+1} (raw)")
            self._text_view.setPlainText(raw)

    # ------------------------------------------------------------------
    # Audio Preview
    # ------------------------------------------------------------------

    def _on_audio_preview(self) -> None:
        """Generate and load a short audio preview for the selected chapter."""
        idx = self._chapter_list.currentRow()
        if idx < 0:
            return

        if not self.project_manager:
            QMessageBox.warning(self, "Audio Preview", "No project is currently loaded.")
            return

        ctrl = self.project_manager.create_pipeline_controller()
        try:
            audio_path = ctrl.tts_generate([idx], preview_mode=True)
        except Exception as exc:
            self.log.log(f"Error during TTS preview: {exc}", level="ERROR")
            QMessageBox.critical(self, "Audio Preview", f"Failed to generate preview audio:\n{exc}")
            return

        if not audio_path:
            QMessageBox.warning(self, "Audio Preview", "TTS preview did not return a file path.")
            return

        audio_path = getattr(audio_path, "resolve", lambda: audio_path)()
        audio_str = str(audio_path)

        # Load into media player
        self._audio_player.setSource(QUrl.fromLocalFile(audio_str))
        self._audio_player.play()

        self.log.log(f"Playing audio preview for chapter {idx+1}: {audio_str}", level="INFO")

    def _on_audio_play(self) -> None:
        """Resume or start playback of the current preview."""
        if self._audio_player.source().isEmpty():
            self._on_audio_preview()
            return
        self._audio_player.play()

    def _on_audio_pause(self) -> None:
        """Pause playback."""
        self._audio_player.pause()

    def _on_audio_stop(self) -> None:
        """Stop playback."""
        self._audio_player.stop()
        
    # ------------------------------------------------------------------
    # Segment-level audio preview (called from EPUB dialog)
    # ------------------------------------------------------------------

    def play_segment_preview(self, chapter_index: int, segment_index: int) -> None:
        """Called by the EPUB preview dialog when a segment is clicked.

        - Selects the chapter in the UI
        - Calls segment-level TTS
        - Plays the resulting audio
        """
        if not self.project_manager:
            QMessageBox.warning(self, "Audio Preview", "No project is currently loaded.")
            return

        # Keep UI in sync
        if 0 <= chapter_index < self._chapter_list.count():
            self._chapter_list.setCurrentRow(chapter_index)

        ctrl = self.project_manager.create_pipeline_controller()

        try:
            audio_path = ctrl.tts_generate_segment(chapter_index, segment_index, preview_mode=True)
        except Exception as exc:
            self.log.log(f"Error during segment preview: {exc}", level="ERROR")
            QMessageBox.critical(self, "Audio Preview", f"Failed to generate segment preview:\n{exc}")
            return

        if not audio_path:
            QMessageBox.warning(self, "Audio Preview", "Segment preview did not return a file path.")
            return

        audio_path = getattr(audio_path, "resolve", lambda: audio_path)()
        audio_str = str(audio_path)

        self._audio_player.setSource(QUrl.fromLocalFile(audio_str))
        self._audio_player.play()

        self.log.log(
            f"Playing segment preview: chapter={chapter_index+1}, segment={segment_index}, file={audio_str}",
            level="INFO",
        )


    # ------------------------------------------------------------------
    # Reprocessing actions
    # ------------------------------------------------------------------

    def _on_reclean(self) -> None:
        """Re-run deterministic cleaning for this chapter."""
        idx = self._chapter_list.currentRow()
        if idx < 0:
            return

        ctrl = self.project_manager.create_pipeline_controller()
        ctrl.clean_chapters([idx])
        ctrl.plan_clean_review()

        self.log.log(f"Re-cleaned chapter {idx+1}.", level="SUCCESS")
        self._on_chapter_selected(idx)

    def _on_resemantic(self) -> None:
        """Re-run semantic LLM analysis for this chapter."""
        idx = self._chapter_list.currentRow()
        if idx < 0:
            return

        ctrl = self.project_manager.create_pipeline_controller()
        ctrl.llm_semantic_analysis([idx])
        ctrl.normalize_llm_output([idx])
        ctrl.smart_review_dialogue([idx])

        self.log.log(f"Re-ran semantic analysis for chapter {idx+1}.", level="SUCCESS")
        self._on_chapter_selected(idx)

    # ------------------------------------------------------------------
    # EPUB Preview
    # ------------------------------------------------------------------

    def _on_epub_preview(self) -> None:
        """Open a dialog to preview EPUB-related artifacts for this chapter."""
        idx = self._chapter_list.currentRow()
        if idx < 0:
            return

        if not self.project_manager:
            QMessageBox.warning(self, "EPUB Preview", "No project is currently loaded.")
            return

        work_dir = self.project_manager.get_work_dir()
        chapters = self.project_manager.get_chapters() or []
        max_chapters = len(chapters)

        dlg = EpubChapterPreviewDialog(self, work_dir, idx, max_chapters)
        dlg.exec()


