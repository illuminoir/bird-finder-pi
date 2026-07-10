import os
import threading
from flask import Flask, render_template, request, jsonify

from dotenv import load_dotenv
load_dotenv()

from db import (
    init_db,
    get_recent_detections,
    get_species_stats,
    get_bird_of_the_day,
    get_total_detections,
    get_total_species,
    get_latest_detection_excluding,
    get_activity_heatmap,
    get_latest_rare_detection,
    get_species_detail,
    get_species_cache,
    save_species_cache,
    get_life_list, save_removed_bg,
)
from data_util import get_wikipedia_image, get_wikipedia_extract, get_xeno_canto_sounds, remove_background
from datetime import datetime, timezone, timedelta
import requests

app = Flask(__name__)

import queue

_rembg_queue          = queue.Queue()
_rembg_worker_started = False

def _rembg_worker():
    while True:
        species, url = _rembg_queue.get()
        print(f"[rembg] processing {species}...")
        result_url = remove_background(url)
        if result_url:
            save_removed_bg(species, result_url)
            print(f"[rembg] done {species}")
        _rembg_queue.task_done()

# ----------------------------
# CONFIG
# ----------------------------

EXCLUDED_SPECIES = []

HEATMAP_HOURS = [
    "12am", "1am", "2am", "3am", "4am", "5am", "6am", "7am", "8am", "9am", "10am", "11am",
    "12pm", "1pm", "2pm", "3pm", "4pm", "5pm", "6pm", "7pm", "8pm", "9pm", "10pm", "11pm",
]

HEATMAP_HOUR_MAP = {
    "12am": 0,  "1am": 1,  "2am": 2,  "3am": 3,
    "4am":  4,  "5am": 5,  "6am": 6,  "7am": 7,
    "8am":  8,  "9am": 9,  "10am": 10, "11am": 11,
    "12pm": 12, "1pm": 13, "2pm": 14, "3pm": 15,
    "4pm":  16, "5pm": 17, "6pm": 18, "7pm": 19,
    "8pm":  20, "9pm": 21, "10pm": 22, "11pm": 23,
}

HEATMAP_PALETTE = [
    "#1a3d22",
    "#166534",
    "#15803d",
    "#16a34a",
    "#22c55e",
    "#4ade80",
]

HEATMAP_DETAIL_LIMIT = 5

# ----------------------------
# HELPERS
# ----------------------------

def time_ago(timestamp_utc_str):
    dt = datetime.fromisoformat(timestamp_utc_str)
    now = datetime.now(timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds // 60}m ago"
    elif seconds < 172800:
        return f"{seconds // 3600}h ago"
    else:
        return f"{seconds // 86400}d ago"


def get_cutoff(range_name):
    now = datetime.now()
    if range_name == "today":
        return now - timedelta(days=1)
    elif range_name == "week":
        return now - timedelta(days=7)
    elif range_name == "month":
        return now - timedelta(days=30)
    return None


def rarity_label(rank, total):
    if rank is None or total is None:
        return None
    pct = rank / total
    if pct >= 0.97:
        return "Extremely Rare"
    elif pct >= 0.90:
        return "Very Rare"
    elif pct >= 0.75:
        return "Rare"
    elif pct >= 0.50:
        return "Uncommon"
    else:
        return "Common"


def build_heatmap(cutoff):
    raw           = get_activity_heatmap(cutoff)
    rows          = {}
    detail        = {}
    species_order = []

    for det in raw:
        sp    = det["species"]
        hour  = datetime.fromisoformat(det["timestamp_utc"]).hour
        label = next(
            (lbl for lbl, start in HEATMAP_HOUR_MAP.items() if start == hour), None
        )
        if label is None:
            continue

        key = (sp, label)
        rows[key] = rows.get(key, 0) + 1

        if key not in detail:
            detail[key] = []
        if len(detail[key]) < HEATMAP_DETAIL_LIMIT:
            detail[key].append({
                "confidence": round(float(det["confidence"]) * 100, 1),
                "time_ago":   time_ago(det["timestamp_utc"])
            })

        if sp not in species_order:
            species_order.append(sp)

    species_order.sort(
        key=lambda s: sum(rows.get((s, h), 0) for h in HEATMAP_HOURS),
        reverse=True
    )
    return rows, detail, species_order


# ----------------------------
# ROUTES
# ----------------------------

@app.route("/")
def index():
    cutoff           = get_cutoff("today")
    latest           = get_latest_detection_excluding(EXCLUDED_SPECIES)
    recent           = get_recent_detections(cutoff)
    stats            = get_species_stats(cutoff)
    bird_of_day      = get_bird_of_the_day()
    total_detections = get_total_detections()
    total_species    = get_total_species()
    rarest           = get_latest_rare_detection()

    latest_formatted = None
    if latest:
        latest_formatted = {
            "species":    latest[0],
            "confidence": round(latest[1] * 100, 1),
            "time_ago":   time_ago(latest[2]),
            "image_url":  get_wikipedia_image(latest[0])
        }

    rarest_formatted = None
    if rarest:
        rarest_formatted = {
            "species":    rarest[0],
            "confidence": round(rarest[1] * 100, 1),
            "time_ago":   time_ago(rarest[2]),
            "rarity":     rarity_label(rarest[3], rarest[4]),
            "image_url":  get_wikipedia_image(rarest[0])
        }

    species_detections = {}
    for r in recent:
        sp = r["species"]
        if sp not in species_detections:
            species_detections[sp] = []
        species_detections[sp].append({
            "confidence": round(float(r["confidence"]) * 100, 1),
            "time_ago":   time_ago(r["timestamp_utc"])
        })

    recent_formatted = [
        {
            "species":        sp,
            "time_ago":       species_detections[sp][0]["time_ago"],
            "all_detections": species_detections[sp]
        }
        for sp in species_detections
    ]

    stats_formatted = [
        {
            "species":   s["species"],
            "count":     s["count"],
            "last_seen": time_ago(s["last_seen"]),
            "rarity":    rarity_label(s.get("rarity_rank"), s.get("rarity_total")),
        }
        for s in stats
    ]

    rows, detail, species = build_heatmap(cutoff)

    return render_template(
        "index.html",
        latest           = latest_formatted,
        rarest           = rarest_formatted,
        bird_of_day      = bird_of_day,
        recent           = recent_formatted,
        stats            = stats_formatted,
        total_detections = total_detections,
        total_species    = total_species,
        rows             = rows,
        detail           = detail,
        species          = species,
        hours            = HEATMAP_HOURS,
        palette          = HEATMAP_PALETTE,
    )


@app.route("/recent-data")
def recent_data():
    range_name = request.args.get("range", "today")
    cutoff     = get_cutoff(range_name)
    recent     = get_recent_detections(cutoff)

    species_detections = {}
    for r in recent:
        sp = r["species"]
        if sp not in species_detections:
            species_detections[sp] = []
        species_detections[sp].append({
            "confidence": round(float(r["confidence"]) * 100, 1),
            "time_ago":   time_ago(r["timestamp_utc"])
        })

    recent_formatted = [
        {
            "species":        sp,
            "time_ago":       species_detections[sp][0]["time_ago"],
            "all_detections": species_detections[sp]
        }
        for sp in species_detections
    ]

    return render_template("partials/recent_table.html", recent=recent_formatted)


@app.route("/species-data")
def species_data():
    range_name = request.args.get("range", "today")
    cutoff     = get_cutoff(range_name)
    stats      = get_species_stats(cutoff)

    stats_formatted = [
        {
            "species":   s["species"],
            "count":     s["count"],
            "last_seen": time_ago(s["last_seen"]),
            "rarity":    rarity_label(s.get("rarity_rank"), s.get("rarity_total")),
        }
        for s in stats
    ]

    return render_template("partials/species_table.html", stats=stats_formatted)


@app.route("/activity-data")
def activity_data():
    range_name            = request.args.get("range", "today")
    cutoff                = get_cutoff(range_name)
    rows, detail, species = build_heatmap(cutoff)

    return render_template(
        "partials/activity_heatmap.html",
        rows    = rows,
        detail  = detail,
        species = species,
        hours   = HEATMAP_HOURS,
        palette = HEATMAP_PALETTE,
    )


@app.route("/species-detail")
def species_detail():
    species = request.args.get("name", "")
    if not species:
        return jsonify({"error": "no species provided"}), 400

    db_data = get_species_detail(species)
    info    = db_data.get("info", {})

    cached = get_species_cache(species)
    if cached:
        image_url   = cached["image_url"]
        description = cached["description"]
        sounds      = cached["sounds"]
    else:
        results = {}

        def fetch_image():
            results["image_url"] = get_wikipedia_image(species)

        def fetch_desc():
            results["description"] = get_wikipedia_extract(species)

        def fetch_sounds():
            results["sounds"] = get_xeno_canto_sounds(species)

        threads = [
            threading.Thread(target=fetch_image),
            threading.Thread(target=fetch_desc),
            threading.Thread(target=fetch_sounds),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        image_url   = results.get("image_url")
        description = results.get("description")
        sounds      = results.get("sounds", [])

        save_species_cache(species, image_url, description, sounds)

    return jsonify({
        "species":     species,
        "image_url":   image_url,
        "description": description,
        "rarity":      rarity_label(info.get("rarity_rank"), info.get("rarity_total")),
        "stats":       db_data["stats"],
        "recent":      db_data["recent"],
        "sounds":      sounds,
    })


@app.route("/species-cache-check")
def species_cache_check():
    species = request.args.get("name", "")
    cached = get_species_cache(species)
    return jsonify({"cached": cached is not None})


@app.route("/debug/sounds")
def debug_sounds():
    species = request.args.get("name", "Eurasian Magpie")
    query   = f'en:"{species}" cnt:"United Kingdom"'
    try:
        resp = requests.get(
            "https://xeno-canto.org/api/3/recordings",
            params={"query": query, "key": os.environ.get("XC_API_KEY", "")},
            timeout=8
        )
        return jsonify({
            "status_code": resp.status_code,
            "query_used":  query,
            "raw":         resp.json()
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/debug/clear-cache")
def clear_cache():
    import sqlite3
    conn = sqlite3.connect("birds.db")
    conn.execute("DELETE FROM species_cache")
    conn.commit()
    conn.close()
    return "Cache cleared"


@app.route("/debug/cache")
def debug_cache():
    import sqlite3
    conn = sqlite3.connect("birds.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT species, sounds_json, fetched_at FROM species_cache").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/life-list")
def life_list():
    return render_template("lifelist.html")


@app.route("/life-list-data")
def life_list_data():
    global _rembg_worker_started
    if not _rembg_worker_started:
        threading.Thread(target=_rembg_worker, daemon=True).start()
        _rembg_worker_started = True

    range_name   = request.args.get("range", "all")
    cutoff       = get_cutoff(range_name)
    species_list = get_life_list(min_confidence=0.5, cutoff=cutoff)

    result = []
    for s in species_list:
        result.append({
            "species":        s["species"],
            "count":          s["count"],
            "rarity":         rarity_label(s.get("rarity_rank"), s.get("rarity_total")),
            "image_url":      s["image_url"],
            "removed_bg_url": s["removed_bg_url"],
        })

        if s["image_url"] and not s["removed_bg_url"]:
            _rembg_queue.put((s["species"], s["image_url"]))

    return jsonify(result)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)