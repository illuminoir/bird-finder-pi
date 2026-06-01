from flask import Flask, render_template, request, jsonify
from db import (
    init_db,
    get_recent_detections,
    get_species_stats,
    get_bird_of_the_day,
    get_total_detections,
    get_total_species,
    get_latest_detection_excluding,
    get_last_detection,
    get_activity_heatmap
)
from datetime import datetime, timezone, timedelta
import requests

app = Flask(__name__)

# ----------------------------
# CONFIG
# ----------------------------

EXCLUDED_SPECIES = [
    # Add species you want hidden from Latest Detection
    # e.g. "Eurasian Magpie", "Wood Pigeon"
]

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
    "#1a3d22",  # 0 – no detections
    "#166534",  # 1
    "#15803d",  # 2
    "#16a34a",  # 3
    "#22c55e",  # 4
    "#4ade80",  # 5 – most detections
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


def get_cutoff(range_name):
    now = datetime.now()
    if range_name == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)  # ← midnight today
    elif range_name == "week":
        return now - timedelta(days=7)
    elif range_name == "month":
        return now - timedelta(days=30)
    return None


def build_heatmap(cutoff):
    raw = get_activity_heatmap(cutoff)

    rows          = {}
    detail        = {}
    species_order = []

    for det in raw:
        sp   = det["species"]
        hour = datetime.fromisoformat(det["timestamp_utc"]).hour

        label = next(
            (lbl for lbl, start in HEATMAP_HOUR_MAP.items() if start == hour),
            None
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
    latest           = get_latest_detection_excluding(EXCLUDED_SPECIES)
    cutoff           = get_cutoff("today")
    recent           = get_recent_detections(cutoff)
    stats            = get_species_stats(cutoff)
    bird_of_day      = get_bird_of_the_day()
    total_detections = get_total_detections()
    total_species    = get_total_species()
    last             = get_last_detection()

    last_formatted = None
    if last:
        last_formatted = {
            "species":    last[0],
            "confidence": round(last[1] * 100, 1),
            "time_ago":   time_ago(last[2]),
            "image_url":  get_wikipedia_image(last[0])
        }

    latest_formatted = None
    if latest:
        latest_formatted = {
            "species":    latest[0],
            "confidence": round(latest[1] * 100, 1),
            "time_ago":   time_ago(latest[2]),
            "image_url":  get_wikipedia_image(latest[0])
        }

    species_detections = {}
    for r in recent:
        sp = r["species"]
        if sp not in species_detections:
            species_detections[sp] = []
        species_detections[sp].append({
            "confidence": round(float(r["confidence"]) * 100, 1),
            "time_ago": time_ago(r["timestamp_utc"])
        })

    recent_formatted = [
        {
            "species": r,
            "time_ago": species_detections[r][0]["time_ago"],
            "all_detections": species_detections[r]
        }
        for r in species_detections
    ]

    stats_formatted = [
        {
            "species":   s["species"],
            "count":     s["count"],
            "last_seen": time_ago(s["last_seen"])
        }
        for s in stats
    ]

    rows, detail, species = build_heatmap(get_cutoff("today"))

    return render_template(
        "index.html",
        last             = last_formatted,
        latest           = latest_formatted,
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
            "time_ago": time_ago(r["timestamp_utc"])
        })

    recent_formatted = [
        {
            "species": r,
            "time_ago": species_detections[r][0]["time_ago"],
            "all_detections": species_detections[r]
        }
        for r in species_detections
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
            "last_seen": time_ago(s["last_seen"])
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


@app.route("/api/data")
def api_data():
    latest      = get_latest_detection_excluding(EXCLUDED_SPECIES)
    bird_of_day = get_bird_of_the_day()
    recent      = get_recent_detections(20)
    stats       = get_species_stats()

    latest_formatted = None
    if latest:
        latest_formatted = {
            "species":    latest[0],
            "confidence": round(latest[1] * 100, 1),
            "time_ago":   time_ago(latest[2]),
            "image_url":  get_wikipedia_image(latest[0])
        }

    return jsonify({
        "latest": latest_formatted,
        "bird_of_day": {
            "species": bird_of_day[0],
            "count":   bird_of_day[1]
        } if bird_of_day else None,
        "recent": [
            {
                "id":         r["id"],
                "species":    r["species"],
                "confidence": round(float(r["confidence"]) * 100, 1),
                "time_ago":   time_ago(r["timestamp_utc"])
            }
            for r in recent
        ],
        "stats": [
            {
                "species":   s["species"],
                "count":     s["count"],
                "last_seen": time_ago(s["last_seen"])
            }
            for s in stats
        ],
        "total_detections": get_total_detections(),
        "total_species":    get_total_species()
    })


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)