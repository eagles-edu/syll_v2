#!/usr/bin/env python3
# bin/clear_cache.py
import os
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CacheResetTool")

TARGET_DB_PATHS = [
    "app/data/word_bank.sqlite3",
    "instance/word_bank.sqlite3"
]

def flush_cache_store():
    logger.info("Starting system cache reset operation...")
    deleted_any = False
    for path in TARGET_DB_PATHS:
        if os.path.exists(path):
            try:
                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM words;")
                cursor.execute("DELETE FROM word_syllables;")
                cursor.execute("DELETE FROM word_metadata;")
                cursor.execute("VACUUM;")
                conn.commit()
                conn.close()
                logger.info("Successfully flushed database metrics cache tables at: '%s'", path)
                deleted_any = True
            except Exception as e:
                logger.error("Failed to clear database path '%s': %s", path, str(e))

    if not deleted_any:
        logger.info("No active database caches found.")
    else:
        logger.info("✨ Workspace reset complete.")

if __name__ == "__main__":
    flush_cache_store()
