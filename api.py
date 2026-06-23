import os
import threading
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
    get_activity_heatmap,
    get_latest_rare_detection,
    get_species_detail,
    get_species_cache,
    save_species_cache,
)
from datetime import datetime, timezone, timedelta
import requests

app = Flask(__name__)

# ----------------------------
# CONFIG
# ----------------------------

EXCLUDED_SPECIES = []

EBIRD_API_KEY = os.environ.get("EBIRD_API_KEY", "")
XC_API_KEY    = os.environ.get("XC_API_KEY", "")

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


def get_wikipedia_image(bird_name):
    try:
        headers = {"User-Agent": "BirdFinder/1.0 (bird detection hobby project)"}
        resp = requests.get("https://en.wikipedia.org/w/api.php", headers=headers, params={
            "action":      "query",
            "titles":      bird_name,
            "prop":        "pageimages",
            "pithumbsize": 600,
            "format":      "json",
            "redirects":   1
        }, timeout=5)
        pages = resp.json()["query"]["pages"]
        page  = next(iter(pages.values()))
        return page.get("thumbnail", {}).get("source", None)
    except Exception as e:
        print(f"Wikipedia image error: {e}")
        return None


def get_wikipedia_extract(bird_name):
    try:
        headers = {"User-Agent": "BirdFinder/1.0 (bird detection hobby project)"}
        resp = requests.get("https://en.wikipedia.org/w/api.php", headers=headers, params={
            "action":      "query",
            "titles":      bird_name,
            "prop":        "extracts",
            "exintro":     True,
            "explaintext": True,
            "exsentences": 4,
            "format":      "json",
            "redirects":   1
        }, timeout=5)
        pages = resp.json()["query"]["pages"]
        page  = next(iter(pages.values()))
        return page.get("extract", None)
    except Exception as e:
        print(f"Wikipedia extract error: {e}")
        return None


def get_xeno_canto_sounds(bird_name, limit=3):
    """
    Try progressively looser queries until we get results:
    1. Full name + UK filter
    2. Full name only (any country)
    3. Last word of name + UK filter (e.g. "Magpie")
    """
    queries = [
        f'en:"{bird_name}" cnt:"United Kingdom"',
        f'en:"{bird_name}"',
        f'en:"{bird_name.split()[-1]}" cnt:"United Kingdom"',
    ]
    for query in queries:
        try:
            resp = requests.get(
                "https://xeno-canto.org/api/3/recordings",
                params={"query": query, "key": XC_API_KEY},
                timeout=8
            )
            data = resp.json()
            recordings = data.get("recordings", [])
            if recordings:
                clips = []
                for r in recordings[:limit]:
                    clips.append({
                        "url":       r.get("file") or f"https://xeno-canto.org/{r['id']}/download",
                        "recordist": r.get("rec", "Unknown"),
                        "country":   r.get("cnt", ""),
                        "type":      r.get("type", ""),
                    })
                return clips
        except Exception as e:
            print(f"Xeno-canto error ({query}): {e}")
    return []


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

    # Check cache first
    cached = get_species_cache(species)
    if cached:
        image_url   = cached["image_url"]
        description = cached["description"]
        sounds      = cached["sounds"]
    else:
        # Fetch all three in parallel threads
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

        # Save to cache
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


@app.route("/debug/sounds")
def debug_sounds():
    species = request.args.get("name", "Eurasian Magpie")
    query   = f'en:"{species}" cnt:"United Kingdom"'
    try:
        resp = requests.get(
            "https://xeno-canto.org/api/3/recordings",
            params={"query": query, "key": XC_API_KEY},
            timeout=8
        )
        return jsonify({
            "status_code": resp.status_code,
            "query_used":  query,
            "raw":         resp.json()
        })
    except Exception as e:
        return jsonify({"error": str(e)})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)