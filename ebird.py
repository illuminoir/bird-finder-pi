import requests

EBIRD_BASE = "https://api.ebird.org/v2"
REGION     = "GB-ENG"


def fetch_species_list(api_key: str) -> list[dict]:
    """
    Fetch the full list of species ever recorded in REGION from eBird.
    Returns a list of dicts ordered by eBird taxonomy (most-reported first
    within each family). Position in this list is used as rarity_rank —
    species appearing later are less commonly reported.
    """
    url = f"{EBIRD_BASE}/product/spplist/{REGION}"
    resp = requests.get(url, headers={"X-eBirdApiToken": api_key}, timeout=10)
    resp.raise_for_status()
    codes = resp.json()   # list of speciesCodes in taxonomic/frequency order

    # Fetch taxonomy to map codes → common names
    tax_url = f"{EBIRD_BASE}/ref/taxonomy/ebird"
    tax_resp = requests.get(
        tax_url,
        headers={"X-eBirdApiToken": api_key},
        params={"fmt": "json", "locale": "en"},
        timeout=10
    )
    tax_resp.raise_for_status()
    taxonomy = {t["speciesCode"]: t["comName"] for t in tax_resp.json()}

    result = []
    for rank, code in enumerate(codes):
        common_name = taxonomy.get(code)
        if common_name:
            result.append({
                "ebird_code":   code,
                "common_name":  common_name,
                "rarity_rank":  rank,
                "rarity_total": len(codes),
            })
    return result


def lookup_rarity(species_name: str, api_key: str) -> dict | None:
    """
    Look up rarity rank for a single species name.
    Returns {ebird_code, rarity_rank, rarity_total} or None if not found.

    Fetches the full species list each call — intended to be called once
    per new species and cached in the db immediately after.
    """
    species_list = fetch_species_list(api_key)
    total = len(species_list)

    # Try exact match first, then case-insensitive
    name_lower = species_name.lower()
    for entry in species_list:
        if entry["common_name"].lower() == name_lower:
            return {
                "ebird_code":   entry["ebird_code"],
                "rarity_rank":  entry["rarity_rank"],
                "rarity_total": total,
            }

    return None