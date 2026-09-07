-- PostgreSQL schema for the academic word bank and ESL teaching metadata.
-- Intended for future persistence behind the service layer without changing the current Flask app layout.

CREATE TABLE IF NOT EXISTS words (
    id SERIAL PRIMARY KEY,
    normalized_word TEXT NOT NULL UNIQUE,
    display_word TEXT NOT NULL,
    decoding TEXT NOT NULL,
    formatted TEXT NOT NULL,
    syllable_count INTEGER NOT NULL CHECK (syllable_count > 0),
    stressed_syllable_index INTEGER NOT NULL DEFAULT 0,
    cefr TEXT NOT NULL CHECK (cefr IN ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')),
    source TEXT NOT NULL DEFAULT 'rule-based',
    is_academic BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS word_pronunciations (
    id SERIAL PRIMARY KEY,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    pronunciation_key TEXT NOT NULL,
    ipa TEXT,
    source TEXT NOT NULL DEFAULT 'cmudict',
    UNIQUE (word_id, pronunciation_key)
);

CREATE TABLE IF NOT EXISTS word_syllables (
    id SERIAL PRIMARY KEY,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    syllable_index INTEGER NOT NULL,
    syllable_text TEXT NOT NULL,
    stress_marked BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (word_id, syllable_index)
);

CREATE TABLE IF NOT EXISTS academic_families (
    id SERIAL PRIMARY KEY,
    family_name TEXT NOT NULL UNIQUE,
    root_word TEXT,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS academic_family_members (
    id SERIAL PRIMARY KEY,
    family_id INTEGER NOT NULL REFERENCES academic_families(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL CHECK (relation_type IN ('root', 'derived', 'prefix', 'suffix', 'related')),
    UNIQUE (family_id, word_id, relation_type)
);

CREATE TABLE IF NOT EXISTS word_metadata (
    id SERIAL PRIMARY KEY,
    word_id INTEGER NOT NULL UNIQUE REFERENCES words(id) ON DELETE CASCADE,
    part_of_speech TEXT,
    word_class TEXT,
    frequency_band TEXT,
    academic_level TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_words_normalized_word ON words (normalized_word);
CREATE INDEX IF NOT EXISTS idx_words_cefr ON words (cefr);
CREATE INDEX IF NOT EXISTS idx_words_academic ON words (is_academic);
CREATE INDEX IF NOT EXISTS idx_family_members_word_id ON academic_family_members (word_id);
CREATE INDEX IF NOT EXISTS idx_family_members_family_id ON academic_family_members (family_id);
