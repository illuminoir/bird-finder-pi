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

def get_recent_detections(limit=20):
    """Latest N detections for the live feed."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT species, confidence, timestamp_utc
        FROM detections
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_species_stats():
    """Per-species: total count and last seen timestamp."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT species, COUNT(*) as count, MAX(timestamp_utc) as last_seen
        FROM detections
        GROUP BY species
        ORDER BY last_seen DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_bird_of_the_day():
    """Most detected species today."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT species, COUNT(*) as count
        FROM detections
        WHERE timestamp_utc LIKE ?
        GROUP BY species
        ORDER BY count DESC
        LIMIT 1
    """, (f"{today}%",))
    row = cursor.fetchone()
    conn.close()
    return row

def get_total_detections():
    """Total number of detections ever recorded."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM detections")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_total_species():
    """Total number of unique species ever detected."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT species) FROM detections")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_latest_detection_excluding(excluded_species):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if excluded_species:
        placeholders = ",".join("?" * len(excluded_species))
        cursor.execute(f"""
            SELECT species, confidence, timestamp_utc
            FROM detections
            WHERE species NOT IN ({placeholders})
            ORDER BY id DESC
            LIMIT 1
        """, excluded_species)
    else:
        cursor.execute("""
            SELECT species, confidence, timestamp_utc
            FROM detections
            ORDER BY id DESC
            LIMIT 1
        """)

    row = cursor.fetchone()
    conn.close()
    return row