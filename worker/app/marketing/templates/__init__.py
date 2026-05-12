"""Sentinel content templates — deterministic, state-language-first.

Each template module exports:
  - TEMPLATE_* strings (str.format-friendly)
  - render_*(payload) -> str
  - has_nothing_branch when applicable

Templates do NOT call any LLM. They take a structured payload (state,
signals, source URLs, CTA) and emit a finished string. The LLM-driven
composer in content_factory.py stays in place for X threads / sponsored
content — these templates are for the Sprint 2 channels where output
must be predictable and audit-clean.
"""
