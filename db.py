import sqlite3
import json
from datetime import datetime, timezone, timedelta

DB_PATH = "birds.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            species        TEXT,
            confidence     REAL,
            timestamp_utc  TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS species_info (
            species        TEXT PRIMARY KEY,
            ebird_code     TEXT,
            rarity_rank    INTEGER,
            rarity_total   INTEGER,
            fetched_at     TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS species_cache (
            species      TEXT PRIMARY KEY,
            image_url    TEXT,
            description  TEXT,
            sounds_json  TEXT,
            fetched_at   TEXT
        )
    """)

    conn.commit()
    conn.close()


def insert_detection(species, confidence):
    from ebird import lookup_rarity
    import threading
    import os

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    timestamp = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO detections (species, confidence, timestamp_utc)
        VALUES (?, ?, ?)
    """, (species, confidence, timestamp))
    conn.commit()
    conn.close()

    if not is_species_info_cached(species):
        def fetch():
            api_key = os.environ.get("EBIRD_API_KEY", "")
            if not api_key:
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
            except Exception as e:
                print(f"[eBird] error for {species}: {e}")

        threading.Thread(target=fetch, daemon=True).start()


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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if cutoff:
        cursor.execute("""
            SELECT *
            FROM detections
            WHERE timestamp_utc >= ?
            ORDER BY timestamp_utc DESC
            LIMIT 20
        """, (cutoff,))
    else:
        cursor.execute("""
            SELECT *
            FROM detections
            ORDER BY timestamp_utc DESC
            LIMIT 20
        """)

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_species_stats(cutoff=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if cutoff:
        cursor.execute("""
            SELECT
                d.species,
                COUNT(*) as count,
                MAX(d.timestamp_utc) as last_seen,
                si.rarity_rank,
                si.rarity_total
            FROM detections d
            LEFT JOIN species_info si ON si.species = d.species
            WHERE d.timestamp_utc >= ?
            GROUP BY d.species
            ORDER BY si.rarity_rank ASC NULLS LAST
        """, (cutoff.isoformat(),))
    else:
        cursor.execute("""
            SELECT
                d.species,
                COUNT(*) as count,
                MAX(d.timestamp_utc) as last_seen,
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


def get_bird_of_the_day():
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


def get_latest_rare_detection():
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
          AND CAST(si.rarity_rank AS REAL) / si.rarity_total >= 0.75
        ORDER BY d.timestamp_utc DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return row


def get_total_detections():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM detections")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_total_species():
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
    return [{"species": r[0], "timestamp_utc": r[1], "confidence": r[2]} for r in rows]


def get_species_detail(species: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    now          = datetime.now(timezone.utc)
    cutoff_day   = (now - timedelta(days=1)).isoformat()
    cutoff_week  = (now - timedelta(days=7)).isoformat()
    cutoff_month = (now - timedelta(days=30)).isoformat()

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN timestamp_utc >= ? THEN 1 ELSE 0 END) as today,
            SUM(CASE WHEN timestamp_utc >= ? THEN 1 ELSE 0 END) as week,
            SUM(CASE WHEN timestamp_utc >= ? THEN 1 ELSE 0 END) as month,
            MAX(timestamp_utc) as last_seen
        FROM detections
        WHERE species = ?
    """, (cutoff_day, cutoff_week, cutoff_month, species))
    stats = dict(cursor.fetchone())

    cursor.execute("""
        SELECT confidence, timestamp_utc
        FROM detections
        WHERE species = ?
        ORDER BY timestamp_utc DESC
        LIMIT 10
    """, (species,))
    recent = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT rarity_rank, rarity_total
        FROM species_info
        WHERE species = ?
    """, (species,))
    info = cursor.fetchone()

    conn.close()
    return {
        "stats":  stats,
        "recent": recent,
        "info":   dict(info) if info else {}
    }


# ----------------------------
# SPECIES INFO / RARITY
# ----------------------------

def is_species_info_cached(species: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM species_info WHERE species = ?", (species,))
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


# ----------------------------
# SPECIES CACHE (image/description/sounds)
# ----------------------------

def get_species_cache(species: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM species_cache WHERE species = ?", (species,))
    row = cursor.fetchone()
    conn.close()
    if row:
        row = dict(row)
        row["sounds"] = json.loads(row["sounds_json"] or "[]")
        return row
    return None


def save_species_cache(species: str, image_url, description, sounds: list):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO species_cache (species, image_url, description, sounds_json, fetched_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(species) DO UPDATE SET
            image_url   = excluded.image_url,
            description = excluded.description,
            sounds_json = excluded.sounds_json,
            fetched_at  = excluded.fetched_at
    """, (
        species,
        image_url,
        description,
        json.dumps(sounds),
        datetime.now(timezone.utc).isoformat()
    ))
    conn.commit()
    conn.close()