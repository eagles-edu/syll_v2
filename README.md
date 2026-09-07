# Syllabicator v2 (syll_v2)

A temporary v2 repository for the teaching-first English word analysis app.
It preserves v1’s complete analysis and API surface while adding explicit
development cache control and a cache-status field for v2 bulk responses.

## Features

- Word syllable and stress analysis
- CEFR estimation for learner guidance
- Clean web interface
- REST API for programmatic usage
- Explicit v2 development cache bypass with `?bypass=true`
- Ready for extension with classroom analytics, saved vocabulary, and pronunciation features

## Startup

1. Create and activate a virtual environment using Python 3.10 or newer:
   python3 -m venv .venv
   source .venv/bin/activate
2. Install dependencies:
   pip install -r requirements.txt
3. Install the JavaScript quality tools:
   npm ci
4. Start the app:
   python run.py
5. Open http://localhost:5000 in your browser.

Optional environment variables:

- `SECRET_KEY` — Flask secret key (default: `dev-secret-key`)
- `HOST` — server host (default: `0.0.0.0`)
- `PORT` — server port (default: `5000`)
- `FLASK_ENV` — set to `production` to disable Flask debug mode
- `LOG_FILE` — application log path (default: `logs/app.log`)
- Application log rotation — default maximum size is 18 MiB, with three backups.
- `LOG_LEVEL` — logging level (default: `DEBUG`)
- `TRACE_MARKDOWN_FILE` — human-readable live trace path (default:
  `DYNAMICALLY-log.md`)

The first time the app runs, it may automatically download the NLTK CMU Pronouncing Dictionary if it is not already available locally.

The SQLite word bank is stored at `instance/word_bank.sqlite3` by default. Set
`WORD_BANK_DB_PATH` to use another location. `pytest-cov`, `openpyxl`, and
`odfpy` are included for the test and word-bank export workflows.

When starting locally with `python run.py`, the app will attempt to open your browser automatically unless `OPEN_BROWSER` is set to `0`, `false`, or `no`.

## Logging and analysis traces

The application writes logs to the console and to a rotating file. The default
file is `logs/app.log`; it rotates after 18 MiB and keeps three backup files. To
follow the persistent log while analyzing a word:

  `tail -f logs/app.log`

Set a different destination or reduce the verbosity when needed:

  `LOG_FILE=/tmp/syllabicator.log LOG_LEVEL=INFO python run.py`

Docker users can inspect the same output with:

  `docker compose logs -f syllabicator`

Each raw spelling analysis emits an ordered `analysis_step` event immediately
at `DEBUG` level. Every event records the actual step number, rule, node, input,
output, decision, branch, repetition/pass, and status. The stream includes
normalization, CMU vowel counting, silent-letter detection, affix passes,
cluster/VCV decisions, reconciliation, repairs, stress, and final output. It
is emitted from the executing code path; it is not reconstructed from the
final syllables afterward.

The same events are rendered as readable Markdown in `DYNAMICALLY-log.md`:
each step is a separate section with labelled input/output and decision fields,
followed by a completion section containing the final result. The Markdown
file is updated during execution, not generated afterward.

In v2, development configuration bypasses the word-bank shortcut during
`analyze()` by default. Pass `bypass_cache=False` to `WordAnalysisService` when
testing persisted lookup behavior. The API also accepts `?bypass=true`; bulk
responses include `cache_bypassed` so the client can identify the active path.

For example, a raw `resignation` trace includes the explicit teaching path
`resignation > re-signa-tion`, `signa > signa`, `signa > sig-na`, the repeated
`NFRP` stop, the VCV decision, the final `-ckle`/`-le` guards, stress placement,
and the final decoded output. This is deliberately a decision log, not a list
of internal rule identifiers.

## Docker Compose

Build and run the app with Docker Compose:

  `docker compose up --build`

Then open http://localhost:5000.

Compose keeps the v2 SQLite database, application log, and dynamic Markdown
trace in project-scoped Docker volumes. Inspect them with:

  `docker compose exec syllabicator sh -c 'ls -lh /app/logs /app/traces /app/instance'`

Stop the app and remove containers with:

  `docker compose down`

## Operation

Application Runtime Started
The Flask application server is running in the persistent environment:

Command: `OPEN_BROWSER=0 .venv/bin/python run.py`

- Host: 0.0.0.0
- Port: 5000
- Local URL: http://127.0.0.1:5000
- Endpoint Verification:
- GET /api/health
    → {"status": "ok"}
- POST /api/analyze
    → Successfully tested with bulk input (english, resignation, aqueous), returning expected stress decoding and syllable structures (éng-lish, res-ig-ná-tion, á-que-ous).

Use the web UI at `/` for interactive syllable and stress analysis.

Programmatic API endpoints:

- `GET /api/health` — service health check
- `GET /api/analyze/<word>` — return syllable, stress, and CEFR analysis for `<word>`
- `GET /api/analyze?words=english&words=beautiful` or `POST /api/analyze` with newline-/comma-delimited text or JSON arrays — analyze multiple words in one request
- `POST /api/analyze/bulk` — alias for bulk analysis input

Example API requests:

`curl http://localhost:5000/api/analyze/beautiful`
`curl -X POST http://localhost:5000/api/analyze -H 'Content-Type: application/json' -d '{"words":["english","beautiful","calendar"]}'`
`curl -X POST http://localhost:5000/api/analyze -H 'Content-Type: text/plain' --data-binary $'english\nbeautiful\ncalendar'`

The app keeps the service-layer contract intact and exposes a future-ready schema at `app/data/word_bank_schema.sql` for PostgreSQL-backed word-bank storage, pronunciation metadata, syllable records, and academic family relationships.

## Project structure

- app/
  - routes/
  - services/
  - static/
  - templates/
- bin/
- docs/
- tests/
- tmp/
- run.py

The analysis, pronunciation, persistence, and word-bank format adapters live
in `app/analysis/`, `app/repositories/`, and `app/services/`; the public
`WordAnalysisService` façade remains in `app/services/word_service.py`.

## Notes

This project intentionally keeps the core logic isolated in a service layer so it can be expanded later with additional features such as CSV vocabulary import, classroom dashboards, and pronunciation audio support.
