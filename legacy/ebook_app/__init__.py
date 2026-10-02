# ebook_app/__init__.py
"""
ebook_app — Web Novel to EPUB3 Audiobook converter.

Package layout:
  app/          Application entry point, UI pages, and state management
  pipeline/     Pipeline controller and phase definitions
  text/         Text processing: scrape, parse, translate, segment, identify, emotion
  tts/          TTS engine, voice routing, audio utilities
  epub/         EPUB3 builder (XHTML, SMIL, OPF, TOC, packaging)
  config/       Default JSON configuration files
  logs/         Runtime log outputs
  output/       Generated EPUB and audio output
"""
__version__ = "0.2.0"
