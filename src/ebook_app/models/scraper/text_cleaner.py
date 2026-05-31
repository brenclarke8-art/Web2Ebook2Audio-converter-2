import re

class TextCleaner:
    ZERO_WIDTH_CHARS = [
        "\u200B", "\u200C", "\u200D", "\uFEFF",
        "\u2060", "\u180E",
    ]

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
    def clean_text(text: str) -> str:
        return TextCleaner.normalize_whitespace(
            TextCleaner.remove_zero_width_chars(text)
        )
