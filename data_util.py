import os
import requests

XC_API_KEY = os.environ.get("XC_API_KEY", "")

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
    words = bird_name.replace("-", " ").split()
    name_candidates = [" ".join(words[i:]) for i in range(len(words))]

    queries = []
    for name in name_candidates:
        queries.append(f'en:"{name}" cnt:"United Kingdom"')
        queries.append(f'en:"{name}"')

    print(f"[XC] fetching sounds for '{bird_name}'")
    print(f"[XC] will try {len(queries)} queries: {queries}")

    for query in queries:
        try:
            print(f"[XC] trying: {query}")
            resp = requests.get(
                "https://xeno-canto.org/api/3/recordings",
                params={"query": query, "key": XC_API_KEY},
                timeout=8
            )
            print(f"[XC] status: {resp.status_code}")
            data = resp.json()
            print(f"[XC] numRecordings: {data.get('numRecordings')} recordings in response: {len(data.get('recordings', []))}")
            recordings = data.get("recordings", [])
            if recordings:
                print(f"[XC] matched via: {query}")
                return [
                    {
                        "url":       r.get("file"),
                        "recordist": r.get("rec", "Unknown"),
                        "country":   r.get("cnt", ""),
                        "type":      r.get("type", ""),
                    }
                    for r in recordings[:limit]
                ]
        except Exception as e:
            print(f"[XC] error ({query}): {e}")

    print(f"[XC] no recordings found for '{bird_name}' after all queries")
    return []