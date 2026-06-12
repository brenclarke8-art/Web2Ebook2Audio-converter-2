# ebook_app/text/parse/html_cleaner.py
import re

class TextCleaner:
    ZERO_WIDTH_CHARS = [
        "\u200B", "\u200C", "\u200D", "\uFEFF",
        "\u2060", "\u180E",
    ]
    CONTROL_TOKENS = {
        "raws",
        "translate",
        "forum",
        "reader settings",
        "text",
        "a−",
        "a-",
        "a+",
        "compact",
        "normal",
        "wide",
        "theme",
        "dark",
        "sepia",
        "light",
        "width",
        "default",
        "tools",
        "bottom",
        "top",
        "reset",
        "report bug",
    }
    MIN_CONTROL_MATCHES = 4

    @staticmethod
    def remove_zero_width_chars(text: str) -> str:
        for char in TextCleaner.ZERO_WIDTH_CHARS:
            text = text.replace(char, "")
        return text

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        text = re.sub(r" +", " ", text)
        text = re.sub(r"\n\n+", "\n\n", text)
        text = "\n".join(line.strip() for line in text.split("\n"))
        return text.strip()

    @staticmethod
    def remove_reader_controls(text: str) -> str:
        lines = text.split("\n")
        normalized_lines = [" ".join(line.strip().lower().split()) for line in lines]
        control_matches = sum(1 for line in normalized_lines if line in TextCleaner.CONTROL_TOKENS)
        if control_matches < TextCleaner.MIN_CONTROL_MATCHES:
            return text
        kept = [line for line, normalized in zip(lines, normalized_lines) if normalized not in TextCleaner.CONTROL_TOKENS]
        return "\n".join(kept)

    @staticmethod
    def clean_text(text: str) -> str:
        return TextCleaner.normalize_whitespace(
            TextCleaner.remove_reader_controls(
                TextCleaner.remove_zero_width_chars(text)
            )
        )
