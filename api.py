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
    get_activity_heatmap   # ← new db function (see below)
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

# Hour slots displayed across the heatmap grid
HEATMAP_HOURS = [
    "5am", "6am", "7am", "8am", "9am", "10am",
    "11am", "12pm", "1pm", "2pm", "3pm", "4pm",
]

# Map display label → start hour (24h). Each bucket covers [start, start+1).
HEATMAP_HOUR_MAP = {
    "5am": 5, "6am": 6, "7am": 7, "8am": 8,
    "9am": 9, "10am": 10, "11am": 11, "12pm": 12,
    "1pm": 13, "2pm": 14, "3pm": 15, "4pm": 16,
}

# Six-stop green palette: index = clamped detection count (0–5)
HEATMAP_PALETTE = [
    "#1a3d22",  # 0 – no detections
    "#166534",  # 1
    "#15803d",  # 2
    "#16a34a",  # 3
    "#22c55e",  # 4
    "#4ade80",  # 5 – most detections
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


def get_cutoff(range_name):
    now = datetime.now()
    if range_name == "today":
        return now - timedelta(days=1)
    elif range_name == "week":
        return now - timedelta(days=7)
    elif range_name == "month":
        return now - timedelta(days=30)
    return None  # "all"


def build_heatmap(cutoff):
    """
    Fetch raw detections from the db and bucket them into
    {(species, hour_label): count}, plus an ordered species list.

    get_activity_heatmap(cutoff) should return a list of dicts/rows with:
        row["species"]       – str
        row["timestamp_utc"] – ISO datetime string
    """
    raw = get_activity_heatmap(cutoff)

    rows = {}           # {(species, hour_label): count}
    species_order = []  # deduplicated, insertion order

    for det in raw:
        sp   = det["species"]
        hour = datetime.fromisoformat(det["timestamp_utc"]).hour

        label = next(
            (lbl for lbl, start in HEATMAP_HOUR_MAP.items() if start == hour),
            None
        )
        if label is None:
            continue  # outside display window

        key = (sp, label)
        rows[key] = rows.get(key, 0) + 1

        if sp not in species_order:
            species_order.append(sp)

    # Sort species by total detections, most active first
    species_order.sort(
        key=lambda s: sum(rows.get((s, h), 0) for h in HEATMAP_HOURS),
        reverse=True
    )

    return rows, species_order

# ----------------------------
# ROUTES
# ----------------------------

@app.route("/")
def index():
    latest          = get_latest_detection_excluding(EXCLUDED_SPECIES)
    recent          = get_recent_detections(20)
    stats           = get_species_stats()
    bird_of_day     = get_bird_of_the_day()
    total_detections = get_total_detections()
    total_species   = get_total_species()
    last            = get_last_detection()

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

    recent_formatted = [
        {
            "species":    r["species"],
            "confidence": round(float(r["confidence"]) * 100, 1),
            "time_ago":   time_ago(r["timestamp_utc"])
        }
        for r in recent
    ]

    stats_formatted = [
        {
            "species":   s["species"],
            "count":     s["count"],
            "last_seen": time_ago(s["last_seen"])
        }
        for s in stats
    ]

    # Heatmap defaults to "month" on first load
    heatmap_rows, heatmap_species = build_heatmap(get_cutoff("month"))

    return render_template(
        "index.html",
        last             = last_formatted,
        latest           = latest_formatted,
        bird_of_day      = bird_of_day,
        recent           = recent_formatted,
        stats            = stats_formatted,
        total_detections = total_detections,
        total_species    = total_species,
        # heatmap
        heatmap_rows     = heatmap_rows,
        heatmap_species  = heatmap_species,
        heatmap_hours    = HEATMAP_HOURS,
        heatmap_palette  = HEATMAP_PALETTE,
    )


@app.route("/recent-data")
def recent_data():
    range_name = request.args.get("range", "today")
    cutoff     = get_cutoff(range_name)
    recent     = get_recent_detections(cutoff)

    recent_formatted = [
        {
            "species":    r["species"],
            "confidence": round(float(r["confidence"]) * 100, 1),
            "time_ago":   time_ago(r["timestamp_utc"])
        }
        for r in recent
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
    range_name = request.args.get("range", "month")
    cutoff     = get_cutoff(range_name)

    heatmap_rows, heatmap_species = build_heatmap(cutoff)

    return render_template(
        "partials/activity_heatmap.html",
        rows    = heatmap_rows,
        species = heatmap_species,
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