import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
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
        str(Path(__file__).resolve().parents[1] / "DYNAMICALLY-log.md"),
    )
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/syllabicator",
    )
    database_path: str = os.getenv(
        "WORD_BANK_DB_PATH",
        str(Path(__file__).resolve().parents[1] / "instance" / "word_bank.sqlite3"),
    )
    word_bank_schema_path: str = str(
        (Path(__file__).resolve().parent / "data" / "word_bank_schema.sql")
    )


settings = Config()


__all__ = ["Config", "settings"]
