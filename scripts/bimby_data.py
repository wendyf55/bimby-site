"""
ecoregion tagging and the compact per-source observation files the page loads.

Each source is written to its own file, data/observations-<source>.json:

    {
      "source": "inat", "label": "iNaturalist", "built": "2026-10-13",
      "asOf": "2026-10-13T11:20:00Z",          # when the data was pulled (optional)
      "fields": ["id", "sp", "lat", "lng", "date", "region", "flags"],
      "species": [["Papilio zelicaon", "Anise Swallowtail"], ...],
      "rows": [[334008305, 0, 49.1234, -123.1234, "2026-01-08", 209, 0], ...]
    }

`sp` indexes into `species`; `region` is the ecoregion id (from data/ecoregions.geojson)
or null; `flags` bit 1 = location obscured by the observer (blurred to ~20 km).
Rows are written one per line, sorted by id.
"""
import json
import os
from datetime import date

ECOREGIONS = "data/ecoregions.geojson"
SPECIES_INFO = "data/species-info.json"
NEAREST_MAX_DEG = 0.05   # points just offshore/on the coast snap to a region within ~5 km
FIELDS = ["id", "sp", "lat", "lng", "date", "region", "flags"]
FLAG_OBSCURED = 1


def tag_ecoregions(points):
    """points: list of (lat, lng). Returns a list of ecoregion ids (or None).

    Uses the same simplified outlines the page uses for "Your ecoregion", so a
    record and a clicked spot at the same place always agree. Needs shapely >= 2."""
    import numpy as np
    import shapely
    from shapely.geometry import shape
    from shapely.strtree import STRtree

    geo = json.load(open(ECOREGIONS))
    ids = [f["properties"]["id"] for f in geo["features"]]
    tree = STRtree([shape(f["geometry"]) for f in geo["features"]])
    pts = shapely.points([(lng, lat) for lat, lng in points])
    out = [None] * len(points)
    if not len(points):
        return out
    pi, gi = tree.query(pts, predicate="intersects")
    for p, g in zip(pi, gi):
        if out[p] is None:
            out[p] = ids[g]
    missing = np.array([i for i, r in enumerate(out) if r is None], dtype=int)
    if len(missing):
        pi, gi = tree.query_nearest(pts[missing], max_distance=NEAREST_MAX_DEG)
        for p, g in zip(pi, gi):
            if out[missing[p]] is None:
                out[missing[p]] = ids[g]
    return out


def known_common_names(extra=None):
    """Common names from species-info.json, then `extra` (wins)."""
    names = {}
    if os.path.exists(SPECIES_INFO):
        for sci, e in json.load(open(SPECIES_INFO, encoding="utf-8")).get("species", {}).items():
            if e.get("commonName"):
                names[sci] = e["commonName"]
    names.update(extra or {})
    return names


def write_source(path, source, label, records, as_of=None):
    """records: dicts with id, sci, common, lat, lng, date, and optional obscured.
    Tags ecoregions and writes the compact file. Returns summary counts."""
    records = sorted(records, key=lambda r: r["id"])
    regions = tag_ecoregions([(r["lat"], r["lng"]) for r in records])
    species, sp_index = [], {}
    rows = []
    for r, reg in zip(records, regions):
        if r["sci"] not in sp_index:
            sp_index[r["sci"]] = len(species)
            species.append([r["sci"], r.get("common") or ""])
        elif not species[sp_index[r["sci"]]][1] and r.get("common"):
            species[sp_index[r["sci"]]][1] = r["common"]
        rows.append([r["id"], sp_index[r["sci"]], round(r["lat"], 4), round(r["lng"], 4),
                     r["date"], reg, FLAG_OBSCURED if r.get("obscured") else 0])
    head = {"source": source, "label": label, "built": date.today().isoformat()}
    if as_of:
        head["asOf"] = as_of
    head["fields"] = FIELDS
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(head, ensure_ascii=False)[:-1])
        f.write(',\n"species":' + json.dumps(species, ensure_ascii=False, separators=(",", ":")))
        f.write(',\n"rows":[\n')
        f.write(",\n".join(json.dumps(row, separators=(",", ":")) for row in rows))
        f.write("\n]}\n")
    os.replace(tmp, path)
    untagged = sum(1 for g in regions if g is None)
    print(f"Wrote {len(rows)} records, {len(species)} species -> {path} "
          f"({os.path.getsize(path) // 1024} KB); {untagged} outside the mapped ecoregions")
    return {"records": len(rows), "species": len(species), "untagged": untagged}
