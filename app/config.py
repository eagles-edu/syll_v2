import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:  # pylint: disable=too-many-instance-attributes
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "5000"))
    debug: bool = os.getenv("FLASK_ENV", "development") == "development"
    log_file: str = os.getenv(
        "LOG_FILE",
        str(Path(__file__).resolve().parents[1] / "logs" / "app.log"),
    )
    log_level: str = os.getenv("LOG_LEVEL", "DEBUG")
    markdown_trace_file: str = os.getenv(
        "TRACE_MARKDOWN_FILE",
        str(Path(__file__).resolve().parents[1] / "logs" / "analysis-trace-log.md"),
    )
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/syllabicator",
    )
    database_path: str = os.getenv(
        "WORD_BANK_DB_PATH",
        str(Path(__file__).resolve().parents[1] / "instance" / "word_bank.sqlite3"),
    )
    logic_disagreement_file: str = os.getenv(
        "LOGIC_DISAGREEMENT_FILE",
        str(Path(__file__).resolve().parents[1] / "logs" / "logic-disagreements.jsonl"),
    )
    compound_lexicon_path: str = os.getenv("COMPOUND_LEXICON_PATH", "/usr/share/dict/words")
    merriam_webster_api_key: str = os.getenv(
        "MW_API_KEY",
        os.getenv(
            "MERRIAM_WEBSTER_COLLEGIATE_API_KEY",
            os.getenv("MERRIAM_WEBSTER_LEARNERS_API_KEY", ""),
        ),
    )
    merriam_webster_base_url: str = os.getenv(
        "MERRIAM_WEBSTER_API_BASE_URL",
        "https://www.dictionaryapi.com/api/v3/references/collegiate/json",
    )
    merriam_webster_timeout_seconds: float = float(os.getenv("MERRIAM_WEBSTER_TIMEOUT_SECONDS", "3"))
    word_bank_schema_path: str = str(
        (Path(__file__).resolve().parent / "data" / "word_bank_schema.sql")
    )


settings = Config()


__all__ = ["Config", "settings"]
