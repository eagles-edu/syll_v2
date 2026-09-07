# AGENTS.md

## Project purpose

This repository is a Flask-based English syllable and stress analyzer designed for ESL teaching. The app decodes pronunciation patterns for a word, identifies syllables, highlights stress, and returns a JSON-friendly summary for the web UI and API.

## Start here

- Read `README.md` before making repo-level assumptions.
- Treat `app/services/word_service.py` as the source of truth for the core analysis logic.
- Treat `app/routes/api.py` as the API boundary and keep business logic out of the route layer.
- Treat `tests/test_word_service.py` as the behavior contract for expected word analysis behavior.

## Architecture

- App factory: `app/__init__.py`
- Route blueprints: `app/routes/`
- Business logic: `app/services/word_service.py`
- Web templates: `app/templates/`
- Static assets: `app/static/`
- Entrypoint: `run.py`

## Working rules for this repo

- Keep the service layer responsible for word processing; do not move analysis logic into route handlers.
- Preserve the Flask app factory pattern and blueprint registration in `app/__init__.py`.
- Preserve the contract of `WordAnalysisService.analyze()` and the JSON payload it returns.
- If changing behavior, add or update the relevant test in `tests/test_word_service.py` first.
- Prefer focused fixes in the service layer over broad rewrites.
- Keep API responses consistent with current error handling:
  - invalid input -> `400`
  - missing word/pronunciation -> `404`
  - unexpected server errors -> `500`

## Validation

Run these before finalizing changes:

- `python -m pytest -q`
- `python run.py` for manual smoke testing when behavior changes affect the app runtime

If a change affects packaging or install setup, also verify the environment with:

- `python3 -m venv .venv`
- `source .venv/bin/activate`
- `pip install -r requirements.txt`

## Quality expectations

- Favor small, testable functions over large monolithic logic blocks.
- Keep outputs deterministic for the same word input.
- Do not hardcode special-case fixes for specific example words unless the bug requires it and the test coverage explains it.
- Root-cause fixes are preferred over patching symptoms.

## Notes for AI agents

- Do not introduce broad framework changes unless explicitly requested.
- Do not add unrelated dependencies or rewrite the app structure without a clear reason.
- If the task is ambiguous, identify the exact file, behavior, and failing condition before editing code.
- Keep modifications grounded in the existing repository structure and the current tests.
