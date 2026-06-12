# ebook_app/app/ui/pipeline_view.py
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QThread, Signal
try:
    from PySide6.QtWidgets import QComboBox, QLabel, QMessageBox, QPushButton
except Exception:  # pragma: no cover
    from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton
    class QComboBox:  # type: ignore
        def __init__(self, value=''):
            self._value = value
        def currentText(self):
            return self._value

from ebook_app.app.ui.base_view import BasePage


class _PipelineWorker(QThread):
    RUN_TO_REVIEW = 'run_to_review'
    CONTINUE_AUDIO = 'continue_audio'
    CHECK_INDEX = 'check_index'

    log_message = Signal(str, str)
    inventory_ready = Signal(dict)
    finished_ok = Signal(str, str)
    failed = Signal(str)
    cancelled = Signal(str)

    def __init__(self, *, project_manager, settings, mode, start_ch=1, end_ch=0):
        super().__init__()
        self.project_manager = project_manager
        self.settings = settings
        self.mode = mode
        self._start = start_ch
        self._end = end_ch
        self._cancel_requested = False

    def request_stop(self):
        self._cancel_requested = True

    def _abort_if_cancelled(self) -> bool:
        if self._cancel_requested:
            self.cancelled.emit('Pipeline cancelled by user.')
            return True
        return False

    def _run_to_review(self, ctrl):
        import json as _json

        cached_urls = list(getattr(self.project_manager, 'get_chapter_urls', lambda: [])() or [])
        cached_inventory = getattr(self.project_manager, 'get_inventory', lambda: {})() or {}
        if cached_urls:
            raw_count = int(cached_inventory.get('raw_chapter_count') or len(cached_urls))
            valid_count = int(cached_inventory.get('valid_chapter_count') or 0)
            if valid_count <= 0 or valid_count > len(cached_urls):
                valid_count = len(cached_urls)
            self.inventory_ready.emit({'raw_count': raw_count, 'valid_count': valid_count, 'chapter_urls': cached_urls})
        else:
            # Phase 1 — scrape index, build chapters_raw.json
            ctrl.scrape_index()
            # Read inventory from chapters_raw.json written by scrape_index
            work_dir = getattr(self.project_manager, 'get_work_dir', lambda: None)()
            chapter_urls: list[str] = []
            if work_dir is not None:
                chapters_raw_path = work_dir / 'chapters_raw.json'
                if chapters_raw_path.exists():
                    try:
                        chapters_data = _json.loads(chapters_raw_path.read_text(encoding='utf-8'))
                        chapter_urls = [c.get('source', '') for c in chapters_data if c.get('source')]
                    except Exception:
                        pass
            count = len(chapter_urls)
            self.inventory_ready.emit({'raw_count': count, 'valid_count': count, 'chapter_urls': chapter_urls})

        if self._abort_if_cancelled():
            return

        # Phase 2 — scrape chapter text
        ctrl.scrape_chapters()
        if self._abort_if_cancelled():
            return

        # Phase 3 — deterministic Pass-1 extraction
        ctrl.pass1_extraction()
        if self._abort_if_cancelled():
            return

        # Phase 4 — LLM-based Pass-2 classification
        ctrl.pass2_classification()
        self.finished_ok.emit(self.RUN_TO_REVIEW, 'Processing complete. Review detected characters in the Review tab before audio.')

    def _run_continue_audio(self, ctrl):
        # Phase 5 — rebuild final chapters from reviewed characters
        ctrl.smart_review_dialogue()
        # Phase 6 — TTS audio generation
        ctrl.tts_generate()
        # Phase 7 — EPUB build
        ctrl.epub_build()

    def run(self):
        try:
            ctrl = self.project_manager.create_pipeline_controller()
            if self.mode == self.RUN_TO_REVIEW:
                self._run_to_review(ctrl)
            elif self.mode == self.CONTINUE_AUDIO:
                self._run_continue_audio(ctrl)
                self.finished_ok.emit(self.CONTINUE_AUDIO, 'Audio generation complete.')
        except Exception as exc:
            self.failed.emit(str(exc))


class PipelinePage(BasePage):
    def __init__(self, *, settings, log, project_manager=None, parent=None):
        self._worker = None
        self._stop_btn = None
        self._current_review_chapter_id = None
        self._current_review_segments = []
        self._current_review_row_segment_indexes = []
        self._review_stage_views = {}
        super().__init__(settings=settings, log=log, project_manager=project_manager, parent=parent)

    def _build_ui(self):
        self._layout.addWidget(QLabel('Pipeline'))
        self._stop_btn = QPushButton('Stop')
        self._layout.addWidget(self._stop_btn)
        self._stop_btn.clicked.connect(self._on_stop_pipeline)

    def _set_buttons_enabled(self, enabled: bool):
        if self._stop_btn:
            self._stop_btn.setEnabled(not enabled)

    def _is_busy(self) -> bool:
        if self._worker is None:
            return False
        try:
            return bool(self._worker.isRunning())
        except RuntimeError:
            self._worker = None
            return False

    def _on_worker_finished(self, mode: str, message: str) -> None:
        worker = self._worker
        self._worker = None
        if getattr(self, 'project_manager', None) and worker is not None and hasattr(self.project_manager, 'set_last_processed_chapter'):
            self.project_manager.set_last_processed_chapter(getattr(worker, '_end', 0))
        self._set_buttons_enabled(True)
        if hasattr(self, '_load_active_project_state'):
            self._load_active_project_state()
        if hasattr(self, '_refresh_review_data'):
            self._refresh_review_data()
        self.log.log(message, level='SUCCESS')
        if mode == _PipelineWorker.RUN_TO_REVIEW:
            QMessageBox.information(
                self,
                'Character Review Required',
                "Chapter parsing is complete. Review scraped text and detected characters in the Review tab, then click 'Continue Audio + Export'.",
            )

    def _on_stop_pipeline(self) -> None:
        if not self._is_busy():
            return
        self._worker.request_stop()
        if self._stop_btn:
            self._stop_btn.setEnabled(False)
        self.log.log('Stop requested. Current phase will halt shortly.', level='WARNING')

    @staticmethod
    def _normalize_segment_type(value: str) -> str:
        lowered = (value or '').strip().lower()
        return lowered if lowered in {'dialogue', 'thought', 'narration'} else 'narration'

    @staticmethod
    def _normalize_gender(value: str) -> str:
        lowered = (value or '').strip().lower()
        return lowered if lowered in {'male', 'female'} else 'unknown'

    def _default_voice_for_gender(self, gender: str) -> str:
        if self._normalize_gender(gender) == 'male':
            return self.settings.get('default_male_voice', 'am_adam')
        if self._normalize_gender(gender) == 'female':
            return self.settings.get('default_female_voice', 'af_heart')
        return self.settings.get('narrator_voice', 'af_heart')

    def _character_db_path(self) -> Path:
        return Path(self.project_manager.get_work_dir()) / 'character_database.json'

    def _load_character_database_entries(self) -> list[dict]:
        path = self._character_db_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                pass
        return list(self.settings.get('character_db', []) or [])

    def _collect_review_segments_from_table(self) -> list[dict]:
        collected = []
        for row in range(self._segment_table.rowCount()):
            base_index = self._current_review_row_segment_indexes[row] if row < len(self._current_review_row_segment_indexes) else row
            segment = dict(self._current_review_segments[base_index])
            text_item = self._segment_table.item(row, 0)
            if text_item is not None:
                segment['text'] = text_item.text()
            speaker_widget = self._segment_table.cellWidget(row, 1)
            type_widget = self._segment_table.cellWidget(row, 2)
            segment['speaker'] = speaker_widget.currentText() if speaker_widget is not None else segment.get('speaker', 'unknown')
            segment['type'] = self._normalize_segment_type(type_widget.currentText() if type_widget is not None else segment.get('type', 'narration'))
            collected.append(segment)
        return collected

    def _segments_to_html(self, segments):
        return str(segments)

    def _render_current_segments_preview(self):
        return None

    def _refresh_final_review_view(self, chapter_id: str):
        work_dir = Path(self.project_manager.get_work_dir())
        final_path = work_dir / f'{chapter_id}_chapter_info_final.json'
        if final_path.exists():
            self._review_stage_views['final'] = self._segments_to_html(json.loads(final_path.read_text(encoding='utf-8')).get('segments', []))

    def _on_save_segment_speakers(self) -> None:
        chapter_id = self._current_review_chapter_id
        work_dir = Path(self.project_manager.get_work_dir())
        updated_segments = self._collect_review_segments_from_table()
        mapping = self._current_review_row_segment_indexes or list(range(len(updated_segments)))
        for path in [work_dir / f'{chapter_id}_llm_raw.json', work_dir / f'{chapter_id}_llm_normalized.json', work_dir / f'{chapter_id}_chapter_info_final.json']:
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding='utf-8'))
            segments = payload.get('segments', [])
            for local_idx, segment in enumerate(updated_segments):
                target_idx = mapping[local_idx] if local_idx < len(mapping) else local_idx
                if target_idx < len(segments):
                    segments[target_idx] = dict(segment)
            payload['segments'] = segments
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        self._current_review_segments = updated_segments
        self._render_current_segments_preview()
        self._refresh_final_review_view(chapter_id)
        self.log.log('Saved segment review edits for chapter review.', level='SUCCESS')

    def _on_save_detected_characters(self) -> None:
        existing = {item.get('name'): item for item in self._load_character_database_entries() if isinstance(item, dict) and item.get('name')}
        saved = []
        clamped = 0
        for row in range(self._detected_char_table.rowCount()):
            name_item = self._detected_char_table.item(row, 0)
            conf_item = self._detected_char_table.item(row, 3)
            name = name_item.text().strip() if name_item is not None else ''
            if not name:
                continue
            gender_widget = self._detected_char_table.cellWidget(row, 1)
            voice_widget = self._detected_char_table.cellWidget(row, 2)
            confidence = 0.0
            if conf_item is not None:
                try:
                    confidence = float(conf_item.text())
                except Exception:
                    confidence = 0.0
            if confidence < 0.0 or confidence > 1.0:
                clamped += 1
            existing_entry = existing.get(name, {})
            saved.append({
                'name': name,
                'gender': self._normalize_gender(gender_widget.currentText() if gender_widget is not None else existing_entry.get('gender', 'unknown')),
                'voice': (voice_widget.currentText() if voice_widget is not None else existing_entry.get('voice', '')) or self._default_voice_for_gender(existing_entry.get('gender', 'unknown')),
                'description': existing_entry.get('description', ''),
            })
        path = self._character_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
        self.settings.set('character_db', saved)
        self.settings.set('pending_character_additions', [])
        if hasattr(self.settings, 'save'):
            self.settings.save()
        if hasattr(self, '_refresh_segment_speaker_options'):
            self._refresh_segment_speaker_options()
        level = 'WARNING' if clamped else 'SUCCESS'
        suffix = f' ({clamped} confidence values clamped to 0..1).' if clamped else '.'
        self.log.log(f'Saved character edits{suffix}', level=level)

    def _require_project(self):
        return self.project_manager is not None

    def _on_recheck_dialogue(self) -> None:
        if not self._require_project():
            return
        chapter_id = self._current_review_chapter_id or 'current chapter'
        self.log.log(
            f'Re-running Pass-2 classification and chapter rebuild for {chapter_id}…',
            level='INFO',
        )
        controller = self.project_manager.create_pipeline_controller()
        # Re-run LLM classification then rebuild final chapters from reviewed characters.
        controller.pass2_classification()
        controller.smart_review_dialogue()
        if hasattr(self, '_on_review_chapter_changed') and hasattr(self, '_review_chapter_combo'):
            self._on_review_chapter_changed(self._review_chapter_combo.currentIndex())
        self.log.log('Dialogue recheck complete.', level='SUCCESS')
