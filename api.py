from flask import Flask, jsonify, render_template
from db import (
    init_db,
    get_recent_detections,
    get_species_stats,
    get_bird_of_the_day,
    get_total_detections,
    get_total_species,
    get_latest_detection_excluding,
    get_last_detection
)
from datetime import datetime, timezone
import requests

app = Flask(__name__)

# ----------------------------
# CONFIG
# ----------------------------

EXCLUDED_SPECIES = [
    # Add species you want hidden from Latest Detection
    # e.g. "Eurasian Magpie", "Wood Pigeon"
]

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
    elif seconds < 86400:
        return f"{seconds // 3600}h ago"
    else:
        return f"{seconds // 86400}d ago"


def get_wikipedia_image(bird_name):
    try:
        headers = {"User-Agent": "BirdFinder/1.0 (bird detection hobby project)"}
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "titles": bird_name,
            "prop": "pageimages",
            "pithumbsize": 600,
            "format": "json",
            "redirects": 1
        }
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()
        pages = data["query"]["pages"]
        page = next(iter(pages.values()))
        return page.get("thumbnail", {}).get("source", None)
    except Exception as e:
        print(f"Wikipedia image error: {e}")
        return None


# ----------------------------
# ROUTES
# ----------------------------

@app.route("/")
def index():
    latest = get_latest_detection_excluding(EXCLUDED_SPECIES)
    recent = get_recent_detections(20)
    stats = get_species_stats()
    bird_of_day = get_bird_of_the_day()
    total_detections = get_total_detections()
    total_species = get_total_species()
    last = get_last_detection()
    last_formatted = None

    if last:
        last_image_url = get_wikipedia_image(last[0])
        last_formatted = {
            "species": last[0],
            "confidence": round(last[1] * 100, 1),
            "time_ago": time_ago(last[2]),
            "image_url": last_image_url
        }

    latest_formatted = None
    if latest:
        image_url = get_wikipedia_image(latest[0])
        latest_formatted = {
            "species": latest[0],
            "confidence": round(latest[1] * 100, 1),
            "time_ago": time_ago(latest[2]),
            "image_url": image_url
        }

    recent_formatted = [
        {
            "species": r[0],
            "confidence": round(r[1] * 100, 1),
            "time_ago": time_ago(r[2])
        }
        for r in recent
    ]

    stats_formatted = [
        {
            "species": s[0],
            "count": s[1],
            "last_seen": time_ago(s[2])
        }
        for s in stats
    ]

    return render_template(
        "index.html",
        last=last_formatted,
        latest=latest_formatted,
        bird_of_day=bird_of_day,
        recent=recent_formatted,
        stats=stats_formatted,
        total_detections=total_detections,
        total_species=total_species
    )


@app.route("/api/data")
def api_data():
    latest = get_latest_detection_excluding(EXCLUDED_SPECIES)
    bird_of_day = get_bird_of_the_day()
    recent = get_recent_detections(20)
    stats = get_species_stats()

    latest_formatted = None
    if latest:
        image_url = get_wikipedia_image(latest[0])
        latest_formatted = {
            "species": latest[0],
            "confidence": round(latest[1] * 100, 1),
            "time_ago": time_ago(latest[2]),
            "image_url": image_url
        }

    return jsonify({
        "latest": latest_formatted,
        "bird_of_day": {
            "species": bird_of_day[0],
            "count": bird_of_day[1]
        } if bird_of_day else None,
        "recent": [
            {
                "species": r[0],
                "confidence": round(r[1] * 100, 1),
                "time_ago": time_ago(r[2])
            }
            for r in recent
        ],
        "stats": [
            {
                "species": s[0],
                "count": s[1],
                "last_seen": time_ago(s[2])
            }
            for s in stats
        ],
        "total_detections": get_total_detections(),
        "total_species": get_total_species()
    })


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)