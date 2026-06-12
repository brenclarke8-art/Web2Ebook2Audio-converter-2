# ebook_app/text/translate/prompt_templates.py
"""LLM prompt templates for translation tasks."""

TRANSLATION_SYSTEM_PROMPT = """You are a professional literary translator. Translate the following text from {source_language} to {target_language}.
Preserve paragraph structure, dialogue formatting, and stylistic nuances.
Return a JSON object with a single key "translation" containing the translated text.
"""

CHAPTER_TRANSLATION_PROMPT = """Translate the following chapter excerpt from {source_language} to {target_language}.
Keep character names, dialogue markers, and paragraph breaks intact.
Return JSON: {{"translation": "<translated text>"}}

Text:
{text}
"""

GLOSSARY_AWARE_PROMPT = """Translate from {source_language} to {target_language} using the provided glossary for consistent name/term rendering.

Glossary:
{glossary}

Text:
{text}

Return JSON: {{"translation": "<translated text>"}}
"""
