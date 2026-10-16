"""
Pull research-grade butterfly observations in British Columbia from iNaturalist
into a local cache (data/inat/cache.jsonl). scripts/build_inat.py turns the cache
into data/observations-inat.json for the page.
The cache is not in git: the GitHub Actions workflow keeps it in the Actions cache
(.github/workflows/update-inat.yml). Locally, a first run does a full pull.

What it asks for
    taxon_id=47224 (Papilionoidea, butterflies), place_id=7085 (British Columbia),
    quality_grade=research. Public coordinates only (obscured records are flagged).
    license=cc0,cc-by,cc-by-nc: only observations their observers licensed for
    reuse (the same three licences GBIF accepts). "All rights reserved" and
    NoDerivs / ShareAlike observations are not downloaded. Each record keeps its
    licence code so the build can report the mix.

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
    --time-limit M  Stop a full pull after M minutes and save what it has so far to
                    data/inat/partial.jsonl; the next run picks up where it stopped
                    (a full pull of ~150k records takes about an hour). The cache is
                    only replaced once the full pull is complete.
    If QUERY changes (e.g. the licence filter), the next run is automatically a
    full pull, and the "< 80% of the cache" safety check is skipped for it.

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
LICENSES = ["cc0", "cc-by", "cc-by-nc"]   # reusable observation licences (as GBIF)
QUERY = {"taxon_id": 47224, "place_id": 7085, "quality_grade": "research",
         "license": ",".join(LICENSES),
         "order_by": "id", "order": "asc", "per_page": 200}
QUERY_KEY = json.dumps({k: v for k, v in QUERY.items() if k not in ("order_by", "order", "per_page")},
                       sort_keys=True)   # stored in state.json; a change forces a full pull
USER_AGENT = "butterfly-map/1.0 (UBC Tseng Lab; https://github.com/wendyf55/bimby-site)"
PAUSE = 1.0                         # seconds between requests (iNat asks for ~1/s)
BACKOFF = [10, 30, 60, 120, 300]    # waits before each retry after 429 / 5xx / network error
FULL_EVERY_DAYS = 28
MIN_FULL_RATIO = 0.8

CACHE = "data/inat/cache.jsonl"
STATE = "data/inat/state.json"
PARTIAL = "data/inat/partial.jsonl"   # unfinished full pull: header line, then records


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
            "lat": lat, "lng": lng, "obscured": obscured, "acc": o.get("positional_accuracy"),
            "license": (o.get("license_code") or "").lower() or None}


def walk(extra, max_pages=None, start_id=0, deadline=None, progress=None):
    """Yield slim records for the query, following id_above until the end.
    progress (a dict) gets last_id and done=True/False (False = stopped at deadline)."""
    last_id, pages, seen, total = start_id, 0, 0, None
    progress = progress if progress is not None else {}
    progress.update(last_id=last_id, done=False)
    while True:
        if deadline and time.time() > deadline:
            print(f"Time limit reached after {seen} records; stopping here", flush=True)
            return
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
        if results:
            last_id = results[-1]["id"]
            progress["last_id"] = last_id
        if len(results) < QUERY["per_page"]:
            progress["done"] = True
            break
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


def load_partial():
    """An unfinished full pull: (header, records) or (None, {})."""
    if not os.path.exists(PARTIAL):
        return None, {}
    with open(PARTIAL, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    if not lines or "_resume" not in lines[0]:
        return None, {}
    return lines[0]["_resume"], {r["id"]: r for r in lines[1:]}


def save_partial(head, records):
    tmp = PARTIAL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps({"_resume": head}) + "\n")
        for k in sorted(records):
            f.write(json.dumps(records[k], ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, PARTIAL)


def tell_actions(partial):
    """Let the GitHub Actions workflow know whether this run finished."""
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"partial={'true' if partial else 'false'}\n")


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
    limit = float(args[args.index("--time-limit") + 1]) if "--time-limit" in args else None
    deadline = time.time() + limit * 60 if limit else None
    cache = load_cache()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    started = now_iso()

    query_changed = bool(cache) and state.get("query") != QUERY_KEY
    if query_changed:
        print("The query has changed since the last pull (e.g. the licence filter); doing a full pull")
    full = "--full" in args or not cache or not state.get("lastFull") or query_changed
    if not full:
        last_full = datetime.fromisoformat(state["lastFull"].replace("Z", "+00:00"))
        full = datetime.now(timezone.utc) - last_full > timedelta(days=FULL_EVERY_DAYS)

    head, fresh = load_partial()
    # Resume only an unfinished pull of this same query that started after the last
    # completed full pull (an old leftover is ignored).
    resume = bool(head) and head.get("query") == QUERY_KEY \
        and head.get("started", "") > state.get("lastFull", "")
    if resume and not full:
        print("Found an unfinished full pull; continuing it")
        full = True

    if full:
        if resume:
            started = head["started"]
            print(f"Full pull, continuing after id {head['lastId']} ({len(fresh)} records so far)")
        else:
            head, fresh = {"query": QUERY_KEY, "started": started, "lastId": 0}, {}
            print("Full pull")
        progress = {}
        for r in walk({}, max_pages, head["lastId"], deadline, progress):
            fresh[r["id"]] = r
        if not progress["done"] and not max_pages:
            head["lastId"] = progress["last_id"]
            save_partial(head, fresh)
            tell_actions(partial=True)
            print(f"Saved {len(fresh)} records so far to {PARTIAL}; run again to continue. "
                  "The cache and the site data are unchanged until the pull is complete.")
            return
        if cache and len(fresh) < MIN_FULL_RATIO * len(cache) and not max_pages and not query_changed:
            sys.exit(f"Full pull returned {len(fresh)} records but the cache has {len(cache)}; "
                     "not saving. Check the query or try again later.")
        if os.path.exists(PARTIAL):
            os.remove(PARTIAL)
        removed = len(set(cache) - set(fresh))
        added = len(set(fresh) - set(cache))
        cache = fresh
        state["lastFull"] = started
        if not max_pages:
            state["query"] = QUERY_KEY
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
    tell_actions(partial=False)
    print(f"Cache: {len(cache)} records -> {CACHE}")


if __name__ == "__main__":
    main()
