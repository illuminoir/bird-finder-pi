import sqlite3
from datetime import datetime, timezone

DB_PATH = "birds.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            species TEXT,
            confidence REAL,
            timestamp_utc TEXT
        )
    """)
    conn.commit()
    conn.close()

def insert_detection(species, confidence):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    timestamp = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        INSERT INTO detections (species, confidence, timestamp_utc)
        VALUES (?, ?, ?)
    """, (species, confidence, timestamp))

    conn.commit()
    conn.close()

def get_last_detection():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT species, confidence, timestamp_utc
        FROM detections
        ORDER BY id DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()
    return row