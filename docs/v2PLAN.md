# Syllabicator v2 Logic, MW, Compound, and Idempotency Integration

## Summary

Integrate the useful logic from `docs/syllabification-logic-dev.html` and `tmp/raw3.py` into the existing v2 architecture without executing or copying either wholesale.

MW becomes authoritative whenever its response passes validation. Local CMU/rule/reviewed results remain fallbacks and comparison candidates. Every disagreement is recorded with enough sanitized detail for manual review.

The API payload remains backward-compatible; provenance continues through the existing `source` field.

## Implementation Changes

- Add an injectable `MerriamWebsterProvider` using `MW_API_KEY`, configurable endpoint, timeout, and fail-open behavior. Use the standard library HTTP client; do not add scraping or unnecessary dependencies.
- Validate MW responses strictly:
  - select a matching dictionary entry rather than blindly using the first entry;
  - parse `hwi.hw` separators;
  - require exact spelling-preserving recomposition;
  - validate pronunciation/stress data independently;
  - reject malformed, suggestion-only, mismatched, oversized, or unexpected JSON responses.
- Update the service pipeline:
  1. normalize input;
  2. check validated MW cache/results when enabled;
  3. obtain local reviewed, CMU, compound, and rule-based candidates;
  4. compare candidates;
  5. choose validated MW output when available;
  6. otherwise use the existing local precedence;
  7. persist validated MW results through the existing word-bank upsert path when caching is enabled.
- Preserve reviewed entries as fallback/regression data, not an unconditional override. Existing reviewed words must be compared against MW when MW is enabled.
- Keep `bypass_cache` semantics: bypass persisted word-bank/provider caches while retaining deterministic analysis and fail-open fallback behavior.
- Add a bounded recursive compound resolver backed by packaged `wamerican`:
  - load `/usr/share/dict/words` once;
  - require exact recomposition, minimum component lengths, alphabetic normalization, and CMU vowel evidence for every component;
  - rank candidates deterministically;
  - recurse no deeper than four components;
  - reject no-progress, duplicate, circular, and ambiguous splits;
  - preserve original spelling and explicit hyphenation.
- Ensure examples such as `signpost` are solved through the compound path rather than remaining dependent on a one-word hardcoded patch.
- Correct VCV logic so CMU stress digits are used only for stress level. Vowel length/quality decisions must use the phoneme identity and spelling/rule evidence.
- Add explicit loop/pass limits to affix reduction, nucleus reconciliation, compound recursion, and boundary repair. On exhaustion, return a safe unsplit result and emit a guard event.
- Make analysis state immutable per invocation. Repeated calls with the same normalized input must produce identical syllables, stress, decoding, source, and metadata.
- Make repository writes idempotent through normalized-word upserts. Repeated startup seeding and repeated MW persistence must not create duplicate records.
- Add a dedicated rotating JSONL disagreement log, defaulting to `logs/logic-disagreements.jsonl`. Each event records:
  - normalized word and algorithm version;
  - local candidate(s);
  - MW candidate and sanitized `hw`/pronunciation evidence;
  - validation decisions and rejection reasons;
  - selected result and source;
  - stress comparison;
  - cache/provider status.
- Emit the same disagreement through the live `AnalysisTrace`, so it appears in `logs/analysis-trace-log.md` - create if not present. Never log API keys, authorization headers, or unsanitized exceptions.
- Keep route handlers unchanged as business-logic boundaries. Preserve existing 400/404/500 behavior and single/bulk response shapes.
- Update `.env`, README, Docker configuration, and Compose documentation for MW settings, log paths, cache behavior, and the packaged `wamerican` dependency.
- Update the Docker image to install `wamerican` using `--no-install-recommends`, clean apt metadata, and retain the existing named-volume paths for logs, traces, and the SQLite word bank.
- Keep `npm` tooling limited to existing quality checks; no unrelated frontend rewrite or dependency expansion.

## Tests and Acceptance

- MW parser tests for valid entries, multiple entries, malformed JSON, missing fields, mismatched headwords, invalid separators, missing pronunciation, and timeout/status failures.
- Service tests proving:
  - validated MW output overrides disagreeing reviewed, CMU, compound, and rule-based results;
  - provider failure falls back locally without API failure;
  - no API key disables MW cleanly;
  - cached MW results retain MW provenance;
  - reviewed fallback behavior remains unchanged when MW is unavailable.
- Compound tests for `signpost`, multi-part compounds, false-positive dictionary splits, missing-CMU components, explicit hyphens, and recursion limits.
- Stress tests proving phoneme identity and stress level are not confused with vowel length.
- Trace tests proving real provider, compound, disagreement, fallback, rejection, and loop-guard events are emitted during execution.
- Idempotency tests repeating analysis and persistence multiple times, verifying identical results, stable boundaries, no duplicated hyphens, bounded execution, and unchanged database row counts.
- API regression tests for current single-word, bulk, bypass, invalid-input, missing-word, and error contracts.
- Run:
  - `./.venv/bin/python -m pytest -q`
  - `npm run quality`
  - Docker build and vulnerability scan
  - Compose health check and API smoke tests
  - trace, JSONL, and volume-path verification.

## Assumptions and Defaults

- `MW_API_KEY` is environment-only; no secret is committed.
- MW scraping is not implemented now; the provider interface remains extensible for a future endpoint.
- Validated MW is authoritative even when it conflicts with reviewed data.
- MW failures always fail open.
- Successful MW results persist only through the existing word-bank/cache path.
- Public response shape remains stable; detailed provenance and disagreements remain in `source`, traces, and logs.
- Append-only analysis logs may contain one event per invocation, while computed results and database state remain idempotent.
