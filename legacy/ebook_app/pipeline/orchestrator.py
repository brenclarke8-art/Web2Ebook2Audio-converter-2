from __future__ import annotations

from pathlib import Path

from .run_audio_render import run_file as run_audio_render_file
from .run_llm_process import run_file as run_llm_process_file
from .run_scrape_clean import run_file as run_scrape_clean_file


def run_pipeline(input_json: str | Path, output_dir: str | Path) -> tuple[Path, Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    chapter_clean_path = output_dir / "chapter_clean.json"
    chapter_processed_path = output_dir / "chapter_processed.json"
    chapter_audio_path = output_dir / "chapter_audio.wav"

    run_scrape_clean_file(input_json, chapter_clean_path)
    run_llm_process_file(chapter_clean_path, chapter_processed_path)
    run_audio_render_file(chapter_processed_path, chapter_audio_path)

    return chapter_clean_path, chapter_processed_path, chapter_audio_path
