import sqlite3
import threading
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from ebird import lookup_rarity

DB_PATH = "birds.db"
load_dotenv()

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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS species_info (
            species TEXT PRIMARY KEY,
            ebird_code TEXT,
            rarity_rank INTEGER,   -- position in GB-ENG species list (lower = rarer)
            rarity_total INTEGER,  -- total species in that list (for context)
            fetched_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def _fetch_and_cache_rarity(species: str):
    api_key = os.environ.get("EBIRD_API_KEY", "")
    if not api_key:
        print("[eBird] No EBIRD_API_KEY set — skipping rarity lookup")
        return
    try:
        result = lookup_rarity(species, api_key)
        if result:
            save_species_info(
                species,
                result["ebird_code"],
                result["rarity_rank"],
                result["rarity_total"],
            )
            print(f"[eBird] cached rarity for {species}: rank {result['rarity_rank']}/{result['rarity_total']}")
        else:
            print(f"[eBird] species not found: {species}")
    except Exception as e:
        print(f"[eBird] error fetching rarity for {species}: {e}")


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

    # Trigger rarity lookup in background if this species is new
    if not is_species_info_cached(species):
        threading.Thread(
            target=_fetch_and_cache_rarity,
            args=(species,),
            daemon=True
        ).start()

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

def get_recent_detections(cutoff=None):
    conn = sqlite3.connect("birds.db")
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    if cutoff:
        cursor.execute(
            """
            SELECT *
            FROM detections
            WHERE timestamp_utc >= ?
            ORDER BY timestamp_utc DESC
            LIMIT 20
            """,
            (cutoff,)
        )
    else:
        cursor.execute(
            """
            SELECT *
            FROM detections
            ORDER BY timestamp_utc DESC
            LIMIT 20
            """
        )
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_species_stats(cutoff=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    if cutoff:
        cursor.execute(
            """
            SELECT
                species,
                COUNT(*) as count,
                MAX(timestamp_utc) as last_seen
            FROM detections
            WHERE timestamp_utc >= ?
            GROUP BY species
            ORDER BY count DESC
            """,
            (cutoff.isoformat(),)
        )
    else:
        cursor.execute(
            """
            SELECT
                species,
                COUNT(*) as count,
                MAX(timestamp_utc) as last_seen
            FROM detections
            GROUP BY species
            ORDER BY count DESC
            """
        )

    rows = cursor.fetchall()
    return [dict(row) for row in rows]

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


def get_species_stats(cutoff=None):
    """
    Returns species grouped by detection count, joined with rarity info.
    Sorted by rarity_rank ascending (rarest first).
    Species with no rarity data yet appear at the end.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if cutoff:
        cursor.execute("""
            SELECT
                d.species,
                COUNT(*)            AS count,
                MAX(d.timestamp_utc) AS last_seen,
                si.rarity_rank,
                si.rarity_total
            FROM detections d
            LEFT JOIN species_info si ON si.species = d.species
            WHERE d.timestamp_utc >= ?
            GROUP BY d.species
            ORDER BY si.rarity_rank DESC NULLS LAST
        """, (cutoff.isoformat(),))
    else:
        cursor.execute("""
            SELECT
                d.species,
                COUNT(*)            AS count,
                MAX(d.timestamp_utc) AS last_seen,
                si.rarity_rank,
                si.rarity_total
            FROM detections d
            LEFT JOIN species_info si ON si.species = d.species
            GROUP BY d.species
            ORDER BY si.rarity_rank ASC NULLS LAST
        """)

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_latest_rare_detection():
    """
    Returns the rarest species detected based on eBird rarity_rank.
    Highest rarity_rank = rarest (least commonly reported in GB-ENG).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
            SELECT
                d.species,
                d.confidence,
                d.timestamp_utc,
                si.rarity_rank,
                si.rarity_total
            FROM detections d
            LEFT JOIN species_info si ON si.species = d.species
            WHERE si.rarity_rank IS NOT NULL
              AND CAST(si.rarity_rank AS REAL) / si.rarity_total >= 0.85
            ORDER BY d.timestamp_utc DESC
            LIMIT 1
        """)
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

def get_activity_heatmap(cutoff=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if cutoff:
        cursor.execute("""
            SELECT species, timestamp_utc, confidence
            FROM detections
            WHERE timestamp_utc >= ?
            ORDER BY timestamp_utc
        """, (cutoff.isoformat(),))
    else:
        cursor.execute("""
            SELECT species, timestamp_utc, confidence
            FROM detections
            ORDER BY timestamp_utc
        """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "species": r[0],
            "timestamp_utc": r[1],
            "confidence": r[2],
        }
        for r in rows
    ]


def is_species_info_cached(species: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM species_info WHERE species = ?", (species,)
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def save_species_info(species: str, ebird_code: str, rarity_rank: int, rarity_total: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO species_info (species, ebird_code, rarity_rank, rarity_total, fetched_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(species) DO UPDATE SET
            ebird_code   = excluded.ebird_code,
            rarity_rank  = excluded.rarity_rank,
            rarity_total = excluded.rarity_total,
            fetched_at   = excluded.fetched_at
    """, (species, ebird_code, rarity_rank, rarity_total, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
