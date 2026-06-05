from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

from ebook_app.epub.epub_builder import EPUBBuilder
from ebook_app.models.dialogue_parser import DialogueParser
from ebook_app.scraping.browser_scraper import WebScraper
from ebook_app.scraping.text_cleaner import TextCleaner
from ebook_app.tts.tts_engine import TTSEngine


class PipelineController:
    STEPS = [
        'scrape_index', 'scrape_chapters', 'clean_chapters',
        'plan_clean_review', 'llm_semantic_analysis', 'normalize_llm_output',
        'smart_review_dialogue', 'tts_generate', 'epub_build'
    ]

    def __init__(self, settings, work_dir, on_progress=None):
        self.settings = settings
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.raw_chapter_urls: list[str] = []
        self.chapter_urls: list[str] = []
        self.chapters: list[dict] = []
        self._running = False
        self._start = 1
        self._end = 0
        self._progress_callback = on_progress

    def _emit_progress(self, step: str, percent: int) -> None:
        if self._progress_callback:
            self._progress_callback(step, percent)

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, list):
            return [PipelineController._jsonable(item) for item in value]
        if isinstance(value, dict):
            return {key: PipelineController._jsonable(val) for key, val in value.items()}
        if hasattr(value, '__dict__'):
            return {key: PipelineController._jsonable(val) for key, val in vars(value).items() if not key.startswith('_')}
        return value

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return default

    @staticmethod
    def _chapter_id(index: int) -> str:
        return f'ch{index}'

    @staticmethod
    def _filter_valid_urls(urls):
        return [url for url in urls if 'paywalled' not in str(url).lower()]

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = TextCleaner.clean_text(text or '')
        lines = [line for line in cleaned.splitlines() if line.strip().casefold() not in {'next chapter', 'subscribe now'}]
        return '\n'.join(lines).strip()

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def is_running(self):
        return self._running

    def is_cancelled(self):
        return not self._running

    def set_chapter_range(self, start, end):
        self._start = max(1, int(start))
        self._end = max(0, int(end))

    def set_progress_callback(self, cb):
        self._progress_callback = cb

    def run_all(self):
        for step in self.STEPS:
            getattr(self, step)()

    def scrape_index(self):
        index_url = self.settings.get('index_url', '')
        scraper = WebScraper()
        urls = list(scraper.scrape_index_page(index_url))
        self.raw_chapter_urls = list(urls)
        self.chapter_urls = self._filter_valid_urls(urls)
        self._write_json(self.work_dir / 'raw_chapter_urls.json', self.raw_chapter_urls)
        self._write_json(self.work_dir / 'chapter_urls.json', self.chapter_urls)
        self._emit_progress('scrape_index', 100)

    def get_chapter_inventory(self):
        return {'raw_count': len(self.raw_chapter_urls), 'valid_count': len(self.chapter_urls)}

    def scrape_chapters(self):
        start_idx = self._start - 1
        end_idx = self._end if self._end else len(self.chapter_urls)
        selected = self.chapter_urls[start_idx:end_idx]
        scraper = WebScraper()
        chapters = list(scraper.scrape_chapters(selected))
        self.chapters = chapters
        for i, chapter in enumerate(chapters):
            ch_num = start_idx + i + 1
            chapter_id = self._chapter_id(ch_num)
            (self.work_dir / f'{chapter_id}_raw.txt').write_text(chapter.get('content', ''), encoding='utf-8')
        self._write_json(self.work_dir / 'chapters.json', chapters)
        self._emit_progress('scrape_chapters', 100)

    def clean_chapters(self):
        chapters = self.chapters or self._read_json(self.work_dir / 'chapters.json', [])
        for i, chapter in enumerate(chapters, start=1):
            chapter_id = self._chapter_id(i)
            cleaned = self._clean_text(chapter.get('content', ''))
            (self.work_dir / f'{chapter_id}_cleaned.txt').write_text(cleaned, encoding='utf-8')
        self._emit_progress('clean_chapters', 100)

    def plan_clean_review(self):
        payload = {'needs_review': []}
        self._write_json(self.work_dir / 'clean_review_plan.json', payload)
        self._write_json(self.work_dir / 'semantic_review_plan.json', payload)
        self._emit_progress('plan_clean_review', 100)

    def _build_dialogue_parser(self):
        semantic_model = self.settings.get('dialogue_llm_semantic_model', '')
        legacy_model = self.settings.get('dialogue_llm_model', '')
        model = semantic_model or legacy_model or 'qwen2.5-coder:7b'
        url = self.settings.get('dialogue_llm_url', 'http://127.0.0.1:11434/api/generate')
        return DialogueParser(
            ollama_url=url,
            model=model,
            semantic_model=model,
            fallback_model=model,
            formatter_model=model,
        )

    def _preflight_llm_check(self, parser: DialogueParser) -> None:
        parts = urlsplit(parser.ollama_url)
        tags_url = urlunsplit((parts.scheme, parts.netloc, '/api/tags', '', ''))
        response = requests.get(tags_url, timeout=30)
        response.raise_for_status()
        payload = response.json() if hasattr(response, 'json') else {}
        installed = {item.get('name') for item in payload.get('models', []) if isinstance(item, dict)}
        if parser.model not in installed:
            raise RuntimeError(f'Model {parser.model} is not installed')

    def llm_semantic_analysis(self):
        parser = self._build_dialogue_parser()
        if self.settings.get('llm_preflight_check', False):
            self._preflight_llm_check(parser)
        chapters = self._read_json(self.work_dir / 'chapters.json', self.chapters or [])
        for i, _chapter in enumerate(chapters, start=1):
            chapter_id = self._chapter_id(i)
            cleaned_path = self.work_dir / f'{chapter_id}_cleaned.txt'
            if not cleaned_path.exists():
                continue
            text = cleaned_path.read_text(encoding='utf-8')
            parsed = parser.parse(text, chapter_id=chapter_id)
            payload = {
                'segments': [self._jsonable(seg) for seg in parsed.segments],
                'detected_characters': [self._jsonable(ch) for ch in parsed.detected_characters],
            }
            self._write_json(self.work_dir / f'{chapter_id}_llm_raw.json', payload)
        self._emit_progress('llm_semantic_analysis', 100)

    @staticmethod
    def _normalize_segment(segment: dict) -> dict:
        normalized = dict(segment)
        seg_type = str(normalized.get('type', 'narration')).strip().lower()
        normalized['type'] = seg_type if seg_type in {'dialogue', 'thought', 'narration'} else 'narration'
        gender = str(normalized.get('gender', 'unknown')).strip().lower()
        normalized['gender'] = gender if gender in {'male', 'female'} else 'unknown'
        speaker = str(normalized.get('speaker', 'unknown')).strip()
        while speaker and speaker[-1] in '.,!?;:':
            speaker = speaker[:-1].rstrip()
        normalized['speaker'] = speaker or ('narrator' if normalized['type'] == 'narration' else 'unknown')
        return normalized

    def normalize_llm_output(self):
        chapters = self._read_json(self.work_dir / 'chapters.json', self.chapters or [])
        for i, _chapter in enumerate(chapters, start=1):
            chapter_id = self._chapter_id(i)
            raw = self._read_json(self.work_dir / f'{chapter_id}_llm_raw.json', {})
            normalized = {
                'segments': [self._normalize_segment(seg) for seg in raw.get('segments', [])],
                'detected_characters': raw.get('detected_characters', []),
            }
            self._write_json(self.work_dir / f'{chapter_id}_llm_normalized.json', normalized)
        self._emit_progress('normalize_llm_output', 100)

    def _voice_for_gender(self, gender: str, narrator_voice: str, default_male: str, default_female: str) -> str:
        lowered = (gender or '').strip().lower()
        if lowered == 'male':
            return default_male
        if lowered == 'female':
            return default_female
        return narrator_voice

    def _write_final_chapter_files(self, chapter_id, segments, detected_chars, narrator_voice, default_male, default_female, character_db):
        by_name = {str(item.get('name', '')).casefold(): item for item in character_db if isinstance(item, dict) and item.get('name')}
        final_characters: list[dict] = []
        for item in detected_chars:
            data = self._jsonable(item)
            name = str(data.get('name', '')).strip()
            if not name:
                continue
            key = name.casefold()
            existing = by_name.get(key)
            if existing:
                voice = existing.get('voice', '')
                gender = existing.get('gender', data.get('gender', 'unknown'))
                description = existing.get('description', '')
                record = {**existing, 'name': existing.get('name', name), 'voice': voice, 'gender': gender, 'description': description}
            else:
                voice = self._voice_for_gender(data.get('gender', 'unknown'), narrator_voice, default_male, default_female)
                record = {
                    'name': name,
                    'voice': voice,
                    'gender': data.get('gender', 'unknown') or 'unknown',
                    'description': data.get('description', '') or '',
                }
                character_db.append(record)
                by_name[key] = record
            final_characters.append(record)
        character_lookup = {item['name'].casefold(): item for item in final_characters if item.get('name')}
        final_segments = []
        for item in segments:
            data = self._normalize_segment(self._jsonable(item))
            speaker = data.get('speaker', 'unknown')
            char = character_lookup.get(str(speaker).casefold()) or by_name.get(str(speaker).casefold())
            if char:
                data['voice'] = char.get('voice', narrator_voice)
            else:
                data['voice'] = narrator_voice if data.get('type') == 'narration' else self._voice_for_gender(data.get('gender', 'unknown'), narrator_voice, default_male, default_female)
            final_segments.append(data)
        self._write_json(
            self.work_dir / f'{chapter_id}_chapter_info_final.json',
            {'chapter_id': chapter_id, 'segments': final_segments, 'characters': final_characters},
        )

    def smart_review_dialogue(self):
        chapters = self._read_json(self.work_dir / 'chapters.json', self.chapters or [])
        character_db = self._read_json(self.work_dir / 'character_database.json', list(self.settings.get('character_db', []) or []))
        narrator_voice = self.settings.get('narrator_voice', 'af_heart')
        default_male = self.settings.get('default_male_voice', 'am_adam')
        default_female = self.settings.get('default_female_voice', 'af_heart')
        for i, _chapter in enumerate(chapters, start=1):
            chapter_id = self._chapter_id(i)
            normalized = self._read_json(self.work_dir / f'{chapter_id}_llm_normalized.json', {})
            self._write_final_chapter_files(
                chapter_id=chapter_id,
                segments=normalized.get('segments', []),
                detected_chars=normalized.get('detected_characters', []),
                narrator_voice=narrator_voice,
                default_male=default_male,
                default_female=default_female,
                character_db=character_db,
            )
        self._write_json(self.work_dir / 'character_database.json', character_db)
        self._emit_progress('smart_review_dialogue', 100)

    def _make_tts_backend(self, output_dir=None):
        return TTSEngine(
            output_dir=output_dir or (self.work_dir / 'audio'),
            server_url=self.settings.get('tts_backend_url', 'http://127.0.0.1:5005'),
        )

    def tts_generate(self):
        chapters = self._read_json(self.work_dir / 'chapters.json', self.chapters or [])
        audio_dir = self.work_dir / 'audio'
        audio_dir.mkdir(parents=True, exist_ok=True)
        engine = self._make_tts_backend(output_dir=audio_dir)
        timing: dict[str, Any] = {}
        for i, _chapter in enumerate(chapters, start=1):
            chapter_id = self._chapter_id(i)
            final_data = self._read_json(self.work_dir / f'{chapter_id}_chapter_info_final.json', {})
            files: list[str] = []
            chapter_segments = []
            cursor = 0.0
            for idx, segment in enumerate(final_data.get('segments', [])):
                output_filename = f'{chapter_id}_seg{idx}.wav'
                result = engine.generate_audio(
                    text=segment.get('text', ''),
                    output_filename=output_filename,
                    voice=segment.get('voice') or self.settings.get('narrator_voice', 'af_heart'),
                    speed=float(self.settings.get('tts_speed', 1.0)),
                )
                if self.is_cancelled():
                    return
                if result is not None:
                    files.append(str(result))
                duration = float(engine.get_last_audio_duration() or 0.0)
                chapter_segments.append({
                    'paragraph_id': segment.get('paragraph_id', f'{chapter_id}_p{idx}'),
                    'clip_begin': cursor,
                    'clip_end': cursor + duration,
                })
                cursor += duration
            if files:
                engine.concatenate_audio_files(files, audio_dir / f'{chapter_id}.wav')
            timing[chapter_id] = chapter_segments
        self._write_json(self.work_dir / 'audio_timing.json', timing)
        self._emit_progress('tts_generate', 100)

    def epub_build(self):
        chapters = self._read_json(self.work_dir / 'chapters.json', self.chapters or [])
        output_dir = Path(self.settings.get('output_dir', self.work_dir.parent))
        output_dir.mkdir(parents=True, exist_ok=True)
        builder = EPUBBuilder(
            title=self.settings.get('book_title', 'Book'),
            author=self.settings.get('book_author', 'Author'),
            output_dir=str(output_dir),
            work_dir=str(self.work_dir / 'epub_work'),
        )
        audio_timing = self._read_json(self.work_dir / 'audio_timing.json', {})
        for i, chapter in enumerate(chapters, start=1):
            chapter_id = self._chapter_id(i)
            title = chapter.get('title', f'Chapter {i}')
            cleaned = (self.work_dir / f'{chapter_id}_cleaned.txt').read_text(encoding='utf-8') if (self.work_dir / f'{chapter_id}_cleaned.txt').exists() else ''
            builder.add_chapter(
                filename=f'{chapter_id}.xhtml',
                title=title,
                xhtml=f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><body><p id="{chapter_id}_p0">{cleaned}</p></body></html>',
            )
            audio_path = self.work_dir / 'audio' / f'{chapter_id}.wav'
            if audio_path.exists():
                builder.add_audio(chapter_filename=f'{chapter_id}.xhtml', audio_path=str(audio_path), segments=audio_timing.get(chapter_id, []))
        builder.build()
        self._emit_progress('epub_build', 100)

    def recheck_dialogue_with_manual_context(self, chapter_id, hints):
        cleaned_path = self.work_dir / f'{chapter_id}_cleaned.txt'
        text = cleaned_path.read_text(encoding='utf-8') if cleaned_path.exists() else ''
        result = self._build_dialogue_parser().parse(text, chapter_id, manual_segment_hints=hints)
        payload = {
            'segments': [self._jsonable(seg) for seg in result.segments],
            'detected_characters': [self._jsonable(ch) for ch in result.detected_characters],
        }
        self._write_json(self.work_dir / f'{chapter_id}_llm_raw.json', payload)
        self._write_json(self.work_dir / f'{chapter_id}_llm_normalized.json', {
            'segments': [self._normalize_segment(seg) for seg in payload['segments']],
            'detected_characters': payload['detected_characters'],
        })
        return {'chapter_id': chapter_id, 'segment_count': len(payload['segments']), 'character_count': len(payload['detected_characters'])}
