"""
Pull research-grade butterfly observations in British Columbia from iNaturalist
into a local cache (data/inat/cache.jsonl). scripts/build_inat.py turns the cache
into data/observations-inat.json for the page.

What it asks for
    taxon_id=47224 (Papilionoidea, butterflies), place_id=7085 (British Columbia),
    quality_grade=research. Public coordinates only (obscured records are flagged).

How it pages (iNaturalist API recommended practices,
https://www.inaturalist.org/pages/api+recommended+practices)
    The API won't page past 10,000 results, so instead of page numbers we sort by
    id and ask for the 200 records after the last id seen (id_above). About one
    request per second, one at a time, with a User-Agent that names the project;
    on 429 "Too Many Requests" or a server error it backs off and retries.

Modes
    (default)   Incremental if there is a cache and the last full pull is under
                28 days old: only records created or changed since the last run
                (updated_since, with a day of overlap). Otherwise a full pull.
    --full      Re-walk everything and replace the cache. This is what drops
                deleted observations and ones that are no longer research grade
                or no longer butterflies (incremental runs can't see those).
    --max-pages N   Stop after N requests (for testing).

Nothing is written unless the run finishes. A full pull that returns far fewer
records than the cache already has (< 80%) is treated as an error and not saved.

Standard library only. Run from the repo root:
    python3 scripts/fetch_inat.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = os.environ.get("INAT_API", "https://api.inaturalist.org/v1") + "/observations"
QUERY = {"taxon_id": 47224, "place_id": 7085, "quality_grade": "research",
         "order_by": "id", "order": "asc", "per_page": 200}
USER_AGENT = "BIMBY-butterfly-map/1.0 (UBC Tseng Lab; https://github.com/wendyf55/bimby-site)"
PAUSE = 1.0                         # seconds between requests (iNat asks for ~1/s)
BACKOFF = [10, 30, 60, 120, 300]    # waits before each retry after 429 / 5xx / network error
FULL_EVERY_DAYS = 28
MIN_FULL_RATIO = 0.8

CACHE = "data/inat/cache.jsonl"
STATE = "data/inat/state.json"


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_page(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(len(BACKOFF) + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == len(BACKOFF):
                raise
            wait = BACKOFF[attempt]
            ra = e.headers.get("Retry-After")
            if ra and ra.isdigit():
                wait = max(wait, int(ra))
            print(f"  HTTP {e.code}; waiting {wait}s before retrying", flush=True)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == len(BACKOFF):
                raise
            wait = BACKOFF[attempt]
            print(f"  network error ({e}); waiting {wait}s before retrying", flush=True)
        time.sleep(wait)


def slim(o):
    """Keep only what the build needs (raw taxon, so name mapping can be redone)."""
    t = o.get("taxon") or {}
    lat = lng = None
    if o.get("geojson") and o["geojson"].get("coordinates"):
        lng, lat = o["geojson"]["coordinates"][:2]
    elif o.get("location"):
        lat, lng = (float(x) for x in o["location"].split(","))
    obscured = bool(o.get("obscured")) or o.get("geoprivacy") == "obscured" \
        or o.get("taxon_geoprivacy") == "obscured"
    return {"id": o["id"], "updated": o.get("updated_at"), "date": o.get("observed_on"),
            "name": t.get("name"), "rank": t.get("rank"), "common": t.get("preferred_common_name"),
            "lat": lat, "lng": lng, "obscured": obscured, "acc": o.get("positional_accuracy")}


def walk(extra, max_pages=None):
    """Yield slim records for the query, following id_above until the end."""
    last_id, pages, seen, total = 0, 0, 0, None
    while True:
        data = get_page({**QUERY, **extra, "id_above": last_id})
        pages += 1
        if total is None:
            total = data.get("total_results")
            print(f"{total} records to fetch", flush=True)
        results = data.get("results") or []
        for o in results:
            yield slim(o)
        seen += len(results)
        if pages % 10 == 0:
            print(f"  {seen}/{total}", flush=True)
        if len(results) < QUERY["per_page"]:
            break
        last_id = results[-1]["id"]
        if max_pages and pages >= max_pages:
            print(f"Stopping after {pages} pages (--max-pages)")
            break
        time.sleep(PAUSE)
    print(f"Fetched {seen} records in {pages} requests")


def load_cache():
    if not os.path.exists(CACHE):
        return {}
    with open(CACHE, encoding="utf-8") as f:
        return {r["id"]: r for r in (json.loads(line) for line in f if line.strip())}


def save(cache, state):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for k in sorted(cache):
            f.write(json.dumps(cache[k], ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, CACHE)
    with open(STATE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def main():
    args = sys.argv[1:]
    max_pages = int(args[args.index("--max-pages") + 1]) if "--max-pages" in args else None
    cache = load_cache()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    started = now_iso()

    full = "--full" in args or not cache or not state.get("lastFull")
    if not full:
        last_full = datetime.fromisoformat(state["lastFull"].replace("Z", "+00:00"))
        full = datetime.now(timezone.utc) - last_full > timedelta(days=FULL_EVERY_DAYS)

    if full:
        print("Full pull")
        fresh = {r["id"]: r for r in walk({}, max_pages)}
        if cache and len(fresh) < MIN_FULL_RATIO * len(cache) and not max_pages:
            sys.exit(f"Full pull returned {len(fresh)} records but the cache has {len(cache)}; "
                     "not saving. Check the query or try again later.")
        removed = len(set(cache) - set(fresh))
        added = len(set(fresh) - set(cache))
        cache = fresh
        state["lastFull"] = started
        print(f"{added} new, {removed} no longer in the results")
    else:
        since = datetime.fromisoformat(state["lastRun"].replace("Z", "+00:00")) - timedelta(days=1)
        print(f"Incremental pull: changed since {since.date()}")
        new = changed = 0
        for r in walk({"updated_since": since.isoformat()}, max_pages):
            if r["id"] in cache:
                changed += r != cache[r["id"]]
            else:
                new += 1
            cache[r["id"]] = r
        print(f"{new} new, {changed} changed")

    state["lastRun"] = started
    state["records"] = len(cache)
    save(cache, state)
    print(f"Cache: {len(cache)} records -> {CACHE}")


if __name__ == "__main__":
    main()
