"""Connection helper for the easylang_p3 database."""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def connect() -> psycopg.Connection:
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    conn.execute(f"SET search_path TO {os.environ.get('DB_SCHEMA', 'p3')}")
    return conn
