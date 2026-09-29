"""
Build data/species-info.json: a short description and a photo for every butterfly
in data/observations.json. Used by all the map pages (index + options A/B/C).

Sources
    Description  Wikipedia — the first paragraph of the species' article
                 (REST "page summary" API). Text is CC BY-SA 4.0; the pages link
                 back to the article.
    Photo        iNaturalist — the species' default taxon photo (the one shown on
                 its iNaturalist species page), or, if that one is "all rights
                 reserved", the first openly licensed photo among the species' other
                 curated iNaturalist photos. Stored with the photographer's credit and
                 licence. If none is licensed, falls back to the Wikipedia lead image
                 (licence + author read from Wikimedia Commons).

Matching
    Names are looked up on iNaturalist first (it tracks current butterfly taxonomy
    and links each taxon to its Wikipedia article). When a subspecies or hybrid
    has no licensed photo or no article, it falls back to the first hybrid parent
    and then to the species. If Wikipedia has no article under the scientific name
    (it sometimes uses an older genus), the common name is tried.

Manual fixes
    Optional data/species-info-overrides.json, keyed by scientific name, e.g.
        { "Colias": { "wikipediaTitle": "Colias" },
          "Some species": { "description": "Our own text…", "photoUrl": "…",
                            "photoAttribution": "(c) …", "photoLicense": "cc-by" } }

Uses only the Python standard library. Needs internet access. Run from the repo root:
    python3 scripts/build_species_info.py            # only fetches species not yet in the file
    python3 scripts/build_species_info.py --refresh  # re-fetch everything
It pauses ~1 s between iNaturalist requests (their API limit), so a full run of
~250 species takes about 5–8 minutes.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

OBS = "data/observations.json"
OUT = "data/species-info.json"
OVERRIDES = "data/species-info-overrides.json"

USER_AGENT = "BIMBY-butterfly-map/1.0 (UBC Tseng Lab; https://github.com/wendyf55/bimby-site)"
INAT_PAUSE = 1.0         # seconds between iNaturalist calls
WIKI_PAUSE = 0.2


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            sys.exit("SSL certificate error. On a Mac with Python from python.org, run\n"
                     "  open '/Applications/Python 3.*/Install Certificates.command'\n"
                     "once (or use Homebrew's python3), then try again.")
        raise


def candidates(name):
    """Exact name first, then the first hybrid parent, then the plain species."""
    base = name.split("×")[0].strip()
    words = base.split()
    out = [name.strip(), base]
    if len(words) > 2:
        out.append(" ".join(words[:2]))
    return list(dict.fromkeys(out))


# ---------- iNaturalist ----------
def inat_taxon(name):
    url = "https://api.inaturalist.org/v1/taxa?per_page=10&q=" + urllib.parse.quote(name)
    data = get_json(url) or {}
    time.sleep(INAT_PAUSE)
    for t in data.get("results", []):
        if t.get("name", "").lower() == name.lower():
            return t
    return None


def inat_photo(taxon):
    """The taxon's default photo if it is openly licensed; otherwise the first
    openly licensed one among the taxon's other curated photos."""
    def pack(p):
        return {
            "url": p.get("medium_url") or p.get("url"),
            "square": p.get("square_url") or p.get("url"),
            "attribution": p.get("attribution"),
            "license": p.get("license_code"),
            "source": "iNaturalist",
            "page": f"https://www.inaturalist.org/taxa/{taxon['id']}",
        }
    p = taxon.get("default_photo")
    if p and p.get("license_code"):              # None = "all rights reserved"
        return pack(p)
    data = get_json(f"https://api.inaturalist.org/v1/taxa/{taxon['id']}") or {}
    time.sleep(INAT_PAUSE)
    for t in data.get("results", [])[:1]:
        for tp in t.get("taxon_photos", []):
            ph = tp.get("photo") or {}
            if ph.get("license_code") and (ph.get("medium_url") or ph.get("url")):
                return pack(ph)
    return None


# ---------- Wikipedia ----------
def wiki_summary(title, must_be_lepidoptera=False):
    url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"), safe="")
    data = get_json(url)
    time.sleep(WIKI_PAUSE)
    if not data or data.get("type") != "standard" or not data.get("extract"):
        return None
    if must_be_lepidoptera:
        # Common names are ambiguous ("Painted lady" is also a plant): only accept
        # an article that says it is about a butterfly/skipper/moth.
        text = (data.get("description", "") + " " + data["extract"][:300]).lower()
        if not re.search(r"butterfl|skipper|lepidoptera|moth", text):
            return None
    return data


def commons_photo(summary):
    """Wikipedia lead image + its licence/author from Commons (fallback photo)."""
    thumb = (summary.get("thumbnail") or {}).get("source")
    orig = (summary.get("originalimage") or {}).get("source", "")
    m = re.search(r"/commons/(?:thumb/)?[0-9a-f]/[0-9a-f]{2}/([^/?]+)", orig or thumb or "")
    if not thumb or not m:
        return None
    filename = urllib.parse.unquote(m.group(1))
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo"
           "&iiprop=extmetadata&titles=" + urllib.parse.quote("File:" + filename))
    data = get_json(url) or {}
    time.sleep(WIKI_PAUSE)
    meta = {}
    for page in (data.get("query", {}).get("pages", {}) or {}).values():
        meta = ((page.get("imageinfo") or [{}])[0]).get("extmetadata", {})
    lic = (meta.get("LicenseShortName") or {}).get("value")
    artist = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip()
    if not lic:
        return None
    return {
        "url": thumb,
        "square": thumb,
        "attribution": f"{artist or 'Unknown author'}, {lic}, via Wikimedia Commons",
        "license": lic.lower().replace(" ", "-"),
        "source": "Wikimedia Commons",
        "page": "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(filename.replace(" ", "_")),
    }


def build_one(sci, common, override):
    entry = {"commonName": common, "inaturalist": None, "wikipedia": None, "photo": None}

    # iNaturalist taxon (+ photo), trying subspecies first then species
    wiki_url, inat_common = None, None
    for name in candidates(sci):
        t = inat_taxon(name)
        if not t:
            continue
        if entry["inaturalist"] is None:
            entry["inaturalist"] = {"id": t["id"], "name": t["name"], "rank": t.get("rank"),
                                    "url": f"https://www.inaturalist.org/taxa/{t['id']}"}
        wiki_url = wiki_url or t.get("wikipedia_url")
        inat_common = inat_common or t.get("preferred_common_name")
        entry["photo"] = entry["photo"] or inat_photo(t)
        if entry["photo"] and wiki_url:
            break

    # Wikipedia description
    titles = []
    if override.get("wikipediaTitle"):
        titles.append(override["wikipediaTitle"])
    if wiki_url and "/wiki/" in wiki_url:
        titles.append(urllib.parse.unquote(wiki_url.split("/wiki/")[1]).replace("_", " "))
    titles += candidates(sci)
    summary = None
    for title in dict.fromkeys(titles):
        summary = wiki_summary(title)
        if summary:
            break
    # Wikipedia sometimes still files a species under an older scientific name
    # (e.g. Speyeria vs Argynnis) — its common name usually redirects correctly.
    if not summary:
        names = [n for n in (common, inat_common) if n]
        names += [n[:1].upper() + n[1:].lower() for n in names]      # "Aphrodite fritillary"
        for title in dict.fromkeys(names):
            summary = wiki_summary(title, must_be_lepidoptera=True)
            if summary:
                break
    if summary:
        entry["wikipedia"] = {
            "title": summary["title"],
            "url": (summary.get("content_urls", {}).get("desktop", {}) or {}).get("page")
                   or "https://en.wikipedia.org/wiki/" + urllib.parse.quote(summary["title"].replace(" ", "_")),
            "extract": summary["extract"].strip(),
        }
        if not entry["photo"]:
            entry["photo"] = commons_photo(summary)

    # Manual overrides win
    if override.get("description"):
        entry["wikipedia"] = {"title": None, "url": override.get("descriptionUrl"),
                              "extract": override["description"], "custom": True}
    if override.get("photoUrl"):
        entry["photo"] = {"url": override["photoUrl"], "square": override["photoUrl"],
                          "attribution": override.get("photoAttribution", ""),
                          "license": override.get("photoLicense", ""),
                          "source": override.get("photoSource", ""), "page": override.get("photoPage")}
    return entry


def main():
    refresh = "--refresh" in sys.argv
    obs = json.load(open(OBS))
    species = {}
    for o in obs:
        species.setdefault(o["scientificName"], o.get("commonName") or "")

    info = {}
    if os.path.exists(OUT) and not refresh:
        info = json.load(open(OUT)).get("species", {})
    overrides = json.load(open(OVERRIDES)) if os.path.exists(OVERRIDES) else {}

    todo = [s for s in sorted(species) if s not in info or s in overrides]
    print(f"{len(species)} species; fetching {len(todo)} ({len(species) - len(todo)} already done)")
    for i, sci in enumerate(todo, 1):
        try:
            info[sci] = build_one(sci, species[sci], overrides.get(sci, {}))
            e = info[sci]
            print(f"[{i}/{len(todo)}] {sci}: "
                  f"{'text' if e['wikipedia'] else 'NO TEXT'}, "
                  f"{'photo (' + e['photo']['source'] + ')' if e['photo'] else 'NO PHOTO'}")
        except Exception as ex:          # keep going; rerun later to fill gaps
            print(f"[{i}/{len(todo)}] {sci}: ERROR {ex}")
        if i % 20 == 0:                  # save progress as we go
            save(info, species)
    save(info, species)

    missing_text = [s for s in species if not (info.get(s) or {}).get("wikipedia")]
    missing_photo = [s for s in species if not (info.get(s) or {}).get("photo")]
    print(f"Done. {len(species) - len(missing_text)}/{len(species)} with a description, "
          f"{len(species) - len(missing_photo)}/{len(species)} with a photo.")
    if missing_text:
        print("No description:", ", ".join(missing_text))
    if missing_photo:
        print("No photo:", ", ".join(missing_photo))


def save(info, species):
    out = {
        "built": date.today().isoformat(),
        "sources": {
            "descriptions": "Wikipedia (CC BY-SA 4.0), first paragraph of each article",
            "photos": "iNaturalist taxon photos (licence per photo); Wikimedia Commons fallback",
        },
        "species": {s: info[s] for s in sorted(info) if s in species},
    }
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
