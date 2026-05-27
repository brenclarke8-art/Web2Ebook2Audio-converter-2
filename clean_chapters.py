#!/usr/bin/env python3
"""Clean scraped chapter text files."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean chapter text files.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(input_dir.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"No .txt files found in {input_dir}")

    for src in files:
        cleaned = clean_text(src.read_text(encoding="utf-8", errors="ignore"))
        dst = output_dir / src.name
        dst.write_text(cleaned, encoding="utf-8")
        print(f"Wrote: {dst}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
