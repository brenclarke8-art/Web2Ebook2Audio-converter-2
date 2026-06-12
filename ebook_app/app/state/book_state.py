# ebook_app/app/state/book_state.py
"""
ebook_app.app.state.book_state

Centralized project state manager that coordinates between:
- BookLibrary (persistent multi-book storage)
- PipelineController (pipeline execution)
- UI components (current session state)

The ProjectManager maintains the currently active book/project and provides
a unified interface for accessing chapter data, audio files, and pipeline state.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from ebook_app.app.state.settings_manager import SettingsManager
from ebook_app.app.state.book_library import BookLibrary

logger = logging.getLogger(__name__)


class ProjectManager(QObject):
    """
    Manages the current project/book state and coordinates between components.

    Signals:
        project_loaded: Emitted when a project is loaded or created
        project_closed: Emitted when the current project is closed
        chapters_updated: Emitted when chapter data changes
        pipeline_state_changed: Emitted when pipeline state changes
    """

    project_loaded = Signal(str)  # book_id
    project_closed = Signal()
    chapters_updated = Signal()
    pipeline_state_changed = Signal(str, int)  # step, progress

    def __init__(self, settings: SettingsManager):
        super().__init__()
        self.settings = settings
        self.output_dir = Path(settings.get("output_dir", "output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Book library for persistent storage
        self.library = BookLibrary(self.output_dir)

        # Current project state
        self.current_book_id: Optional[str] = None
        self.current_project_dir: Optional[Path] = None
        self._project_data: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Project lifecycle
    # ------------------------------------------------------------------

    def create_project(self, title: str, author: str, index_url: str) -> str:
        """
        Create a new project and make it the current project.

        Returns:
            The book_id of the newly created project
        """
        # Add to library
        book_id = self.library.add_book(title, author, index_url)

        # Create project directory
        project_dir = self.output_dir / book_id
        project_dir.mkdir(parents=True, exist_ok=True)

        # Initialize project state file
        project_file = project_dir / "project.json"
        initial_state = {
            "book_id": book_id,
            "title": title,
            "author": author,
            "index_url": index_url,
            "raw_chapter_count": 0,
            "valid_chapter_count": 0,
            "last_processed_chapter": 0,
            "selected_start_chapter": 1,
            "selected_end_chapter": 0,
            "chapter_urls": [],
            "chapters": [],
            "pipeline_step": None,
            "created_at": None,
            "last_opened": None,
        }

        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(initial_state, f, indent=2, ensure_ascii=False)

        # Load as current project
        self.load_project(book_id)

        logger.info(f"Created new project: {book_id}")
        return book_id

    def load_project(self, book_id: str) -> bool:
        """
        Load an existing project as the current project.

        Returns:
            True if successfully loaded, False otherwise
        """
        book_entry = self.library.get_book(book_id)
        if not book_entry:
            logger.warning(f"Book {book_id} not found in library")
            return False

        project_dir = self.output_dir / book_id
        project_file = project_dir / "project.json"

        if not project_file.exists():
            logger.warning(f"Project file not found: {project_file}")
            return False

        try:
            with open(project_file, "r", encoding="utf-8") as f:
                self._project_data = json.load(f)

            self.current_book_id = book_id
            self.current_project_dir = project_dir

            # Update settings with project URL if available
            if "index_url" in self._project_data:
                self.settings.set("index_url", self._project_data["index_url"])

            self.project_loaded.emit(book_id)
            logger.info(f"Loaded project: {book_id}")
            return True

        except Exception as exc:
            logger.error(f"Failed to load project {book_id}: {exc}")
            return False

    def close_project(self) -> None:
        """Close the current project and save state."""
        if self.current_book_id:
            self._save_project_state()
            logger.info(f"Closed project: {self.current_book_id}")

        self.current_book_id = None
        self.current_project_dir = None
        self._project_data = {}
        self.project_closed.emit()

    def _save_project_state(self) -> None:
        """Save the current project state to disk."""
        if not self.current_project_dir:
            return

        project_file = self.current_project_dir / "project.json"
        try:
            with open(project_file, "w", encoding="utf-8") as f:
                json.dump(self._project_data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error(f"Failed to save project state: {exc}")

    # ------------------------------------------------------------------
    # Project data access
    # ------------------------------------------------------------------

    def get_project_info(self) -> Optional[Dict[str, Any]]:
        """Get basic info about the current project."""
        if not self.current_book_id:
            return None

        return {
            "book_id": self.current_book_id,
            "title": self._project_data.get("title", ""),
            "author": self._project_data.get("author", ""),
            "index_url": self._project_data.get("index_url", ""),
        }

    def get_work_dir(self) -> Optional[Path]:
        """Get the pipeline work directory for the current project."""
        if not self.current_project_dir:
            return None

        work_dir = self.current_project_dir / "pipeline_work"
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    def get_chapters(self) -> List[Dict[str, Any]]:
        """Get the list of chapters for the current project."""
        if not self.current_project_dir:
            return []

        # Try loading from pipeline work directory first
        work_dir = self.get_work_dir()
        if work_dir:
            chapters_file = work_dir / "chapters.json"
            if chapters_file.exists():
                try:
                    with open(chapters_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as exc:
                    logger.warning(f"Failed to load chapters from {chapters_file}: {exc}")

        # Fall back to project data
        return self._project_data.get("chapters", [])

    def get_chapter_urls(self) -> List[str]:
        """Get the list of chapter URLs for the current project."""
        if not self.current_project_dir:
            return []

        # Try loading from pipeline work directory first
        work_dir = self.get_work_dir()
        if work_dir:
            urls_file = work_dir / "chapter_urls.json"
            if urls_file.exists():
                try:
                    with open(urls_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as exc:
                    logger.warning(f"Failed to load chapter URLs from {urls_file}: {exc}")

        # Fall back to project data
        return self._project_data.get("chapter_urls", [])

    def get_audio_files(self) -> Dict[int, str]:
        """Get mapping of chapter index to audio file paths."""
        if not self.current_project_dir:
            return {}

        work_dir = self.get_work_dir()
        if not work_dir:
            return {}

        audio_dir = work_dir / "audio"
        if not audio_dir.exists():
            return {}

        # Scan for audio files
        audio_files = {}
        for audio_file in audio_dir.glob("ch*.wav"):
            # Extract chapter number from filename (e.g., ch000.wav -> 0)
            try:
                ch_num = int(audio_file.stem[2:])
                audio_files[ch_num] = str(audio_file)
            except ValueError:
                continue

        return audio_files

    def set_index_url(self, index_url: str) -> None:
        """Persist the project's index URL."""
        if not self.current_project_dir:
            return
        self._project_data["index_url"] = index_url
        self.settings.set("index_url", index_url)
        self._save_project_state()

    def set_inventory(
        self,
        *,
        raw_chapter_count: int,
        valid_chapter_count: int,
        chapter_urls: Optional[List[str]] = None,
    ) -> None:
        """Persist index inventory and optional filtered chapter URLs."""
        if not self.current_book_id:
            return

        self._project_data["raw_chapter_count"] = max(0, int(raw_chapter_count))
        self._project_data["valid_chapter_count"] = max(0, int(valid_chapter_count))
        self._project_data["last_chapter_count"] = max(0, int(valid_chapter_count))
        if chapter_urls is not None:
            self._project_data["chapter_urls"] = chapter_urls
            work_dir = self.get_work_dir()
            if work_dir:
                urls_file = work_dir / "chapter_urls.json"
                with open(urls_file, "w", encoding="utf-8") as f:
                    json.dump(chapter_urls, f, indent=2, ensure_ascii=False)

        self.library.update_inventory(
            self.current_book_id,
            raw_chapter_count=raw_chapter_count,
            valid_chapter_count=valid_chapter_count,
        )
        self._save_project_state()
        self.chapters_updated.emit()

    def get_inventory(self) -> Dict[str, int]:
        """Return inventory/progress metrics for the active project."""
        if not self.current_book_id:
            return {
                "raw_chapter_count": 0,
                "valid_chapter_count": 0,
                "last_processed_chapter": 0,
            }

        book = self.library.get_book(self.current_book_id) or {}
        return {
            "raw_chapter_count": int(
                self._project_data.get("raw_chapter_count", book.get("raw_chapter_count", 0))
            ),
            "valid_chapter_count": int(
                self._project_data.get("valid_chapter_count", book.get("valid_chapter_count", 0))
            ),
            "last_processed_chapter": int(
                self._project_data.get(
                    "last_processed_chapter", book.get("last_processed_chapter", 0)
                )
            ),
        }

    def set_selected_range(self, start_chapter: int, end_chapter: int) -> None:
        """Persist selected chapter range for the active project."""
        if not self.current_project_dir:
            return
        self._project_data["selected_start_chapter"] = max(1, int(start_chapter))
        self._project_data["selected_end_chapter"] = max(0, int(end_chapter))
        self._save_project_state()

    def get_selected_range(self) -> Dict[str, int]:
        """Return selected chapter range for the active project."""
        return {
            "start": int(self._project_data.get("selected_start_chapter", 1)),
            "end": int(self._project_data.get("selected_end_chapter", 0)),
        }

    def set_last_processed_chapter(self, chapter_number: int) -> None:
        """Persist last processed chapter across project and library."""
        if not self.current_book_id:
            return
        chapter_value = max(0, int(chapter_number))
        self._project_data["last_processed_chapter"] = chapter_value
        self.library.update_last_processed(self.current_book_id, chapter_value)
        self._save_project_state()
        self.chapters_updated.emit()

    def update_pipeline_step(self, step: str, progress: int = 0) -> None:
        """Update the current pipeline step and emit signal."""
        self._project_data["pipeline_step"] = step
        self._project_data["last_step_progress"] = progress
        self._save_project_state()
        self.pipeline_state_changed.emit(step, progress)

    def create_pipeline_controller(self, on_progress=None):
        if not self.current_project_dir:
            return None
        from ebook_app.pipeline.controller import PipelineController, PipelineSettings
        work_dir = self.get_work_dir()
        ps = PipelineSettings(
            work_dir=work_dir,
            output_dir=self.output_dir,
            book_title=self._project_data.get("title", ""),
            book_author=self._project_data.get("author", ""),
            llm_base_url=self.settings.get("dialogue_llm_url", ""),
            llm_model=self.settings.get("dialogue_llm_model", ""),
        )
        ctrl = PipelineController(ps)
        if on_progress:
            ctrl.set_progress_callback(on_progress)
        return ctrl

    # ------------------------------------------------------------------
    # Library operations
    # ------------------------------------------------------------------

    def load_chapter_index(self) -> list:
        """Load chapter index from work dir."""
        work_dir = self.get_work_dir()
        if not work_dir:
            return []
        for fname in ("chapters.json", "chapters_raw.json"):
            path = work_dir / fname
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
        return []

    def load_pass2_segments(self, chapter_id: str) -> list:
        work_dir = self.get_work_dir()
        if not work_dir:
            return []
        for fname in (f"{chapter_id}_llm_normalized.json", f"{chapter_id}_pass2.json"):
            path = work_dir / fname
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    return data.get("segments", [])
                except Exception:
                    pass
        return []

    def load_final_chapter(self, chapter_id: str) -> dict:
        work_dir = self.get_work_dir()
        if not work_dir:
            return {}
        for fname in (f"{chapter_id}_chapter_info_final.json", f"{chapter_id}_final.json"):
            path = work_dir / fname
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return {}

    def save_final_chapter(self, chapter_id: str, data: dict) -> None:
        work_dir = self.get_work_dir()
        if not work_dir:
            return
        path = work_dir / f"{chapter_id}_chapter_info_final.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_character_db(self) -> list:
        work_dir = self.get_work_dir()
        if not work_dir:
            return []
        path = work_dir / "character_database.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return list(self.settings.get("character_db", []) or [])

    def save_character_db(self, data: list) -> None:
        work_dir = self.get_work_dir()
        if work_dir:
            path = work_dir / "character_database.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.settings.set("character_db", data)

    def list_all_projects(self) -> List[Dict[str, Any]]:
        """Get list of all projects in the library."""
        return self.library.list_books()

    def delete_project(self, book_id: str) -> bool:
        """
        Delete a project from the library and remove its files.

        Returns:
            True if successfully deleted, False otherwise
        """
        # Close if it's the current project
        if book_id == self.current_book_id:
            self.close_project()

        # Remove from library
        if not self.library.remove_book(book_id):
            return False

        # Remove project directory
        project_dir = self.output_dir / book_id
        if project_dir.exists():
            try:
                import shutil
                shutil.rmtree(project_dir)
                logger.info(f"Deleted project directory: {project_dir}")
            except Exception as exc:
                logger.error(f"Failed to delete project directory: {exc}")

        return True
