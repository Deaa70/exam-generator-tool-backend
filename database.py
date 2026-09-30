import sqlite3
from contextlib import closing

DB_PATH = "exams.db"


def init_db():
    """Create the generations table if it does not exist yet."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                num_questions INTEGER NOT NULL
            )
            """
        )
        conn.commit()


def record_generation(num_questions: int):
    """One row per generated exam, storing only how many questions it had."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO generations (num_questions) VALUES (?)",
            (num_questions,),
        )
        conn.commit()


def get_stats() -> dict:
    """Number of generations + the total number of questions generated."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        (generations, total_questions) = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(num_questions), 0) FROM generations"
        ).fetchone()
        return {"generations": generations, "total_questions": total_questions}