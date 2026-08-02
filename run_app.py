#!/usr/bin/env python3
"""Root-level launcher for Web2Ebook2Audio Converter.

Run with:
    python run_app.py
"""
from __future__ import annotations

import os
import sys

# Ensure the repo root is on the path when invoked directly
sys.path.insert(0, os.path.dirname(__file__))

from ebook_app.core.main import main

if __name__ == "__main__":
    main()
