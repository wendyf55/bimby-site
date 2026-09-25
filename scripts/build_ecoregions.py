"""
Build the ecoregion data used by option-a.html.

Inputs (downloaded manually from AAFC's National Ecological Framework for Canada,
https://sis.agr.gc.ca/cansis/nsdb/ecostrat/gis_data.html):
    data/raw/ecoregion_shp.zip   194 ecoregions (218 polygons), NAD83 lat/long
    data/raw/ecozone_shp.zip     15 ecozones (used for zone names only)
    data/observations.json       built by scripts/build_observations.py

Outputs:
    data/ecoregions.geojson             simplified ecoregion outlines for the map
    data/observation-ecoregions.json    {observation id: ecoregion id}

Requires: pip install pyshp shapely   (shapely >= 2.1 for coverage_simplify)

Run from the repo root:
    python3 scripts/build_ecoregions.py
"""
import io
import json
import os
import zipfile

import shapefile                      # pyshp
import shapely
from shapely.geometry import shape, mapping, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree

RAW = "data/raw"
OBS = "data/observations.json"
OUT_GEO = "data/ecoregions.geojson"
OUT_OBS = "data/observation-ecoregions.json"

SIMPLIFY_DEG = 0.02      # coverage-simplify tolerance (~2 km); shared borders stay shared
DECIMALS = 3             # coordinate rounding in the output (~100 m)
NEAREST_MAX_DEG = 0.05   # points just offshore/on the coast snap to a region within ~5 km

# Tidy a few inconsistent names in the 2003 ecozone attribute table
ZONE_NAME_FIXES = {"Boreal PLain": "Boreal Plain", "MixedWood Plain": "Mixedwood Plain"}


def read_zip_shapefile(zip_path, stem):
    """Read a shapefile straight out of its zip (attributes are latin-1)."""
    with zipfile.ZipFile(zip_path) as z:
        names = {os.path.splitext(n)[1].lower(): n for n in z.namelist() if stem in n.lower()}
        parts = {ext: io.BytesIO(z.read(names[ext])) for ext in (".shp", ".shx", ".dbf")}
    return shapefile.Reader(shp=parts[".shp"], shx=parts[".shx"], dbf=parts[".dbf"], encoding="latin1")


def main():
    # --- Ecozone names ---
    zr = read_zip_shapefile(f"{RAW}/ecozone_shp.zip", "ecozones")
    zone_names = {}
    for rec in zr.records():
        zone_names[rec["ECOZONE"]] = ZONE_NAME_FIXES.get(rec["ZONE_NAME"], rec["ZONE_NAME"])

    # --- Ecoregions: dissolve the 218 polygons into 194 regions ---
    rr = read_zip_shapefile(f"{RAW}/ecoregion_shp.zip", "ecoregions")
    parts, info = {}, {}
    for sr in rr.iterShapeRecords():
        rid = sr.record["ECOREGION"]
        parts.setdefault(rid, []).append(shape(sr.shape.__geo_interface__).buffer(0))
        info[rid] = {"id": rid, "name": sr.record["REGION_NAM"].strip(),
                     "nameFr": sr.record["REGION_NOM"].strip(), "zoneId": sr.record["ECOZONE"]}
    ids = sorted(parts)
    full = [unary_union(parts[i]) for i in ids]
    print(f"{len(ids)} ecoregions across {len(zone_names)} ecozones")

    # --- Tag each observation with its ecoregion (using full-detail outlines) ---
    obs = json.load(open(OBS))
    tree = STRtree(full)
    assign, snapped, outside = {}, 0, 0
    for o in obs:
        pt = Point(o["lng"], o["lat"])
        hit = tree.query(pt, predicate="intersects")
        if len(hit):
            assign[o["id"]] = ids[hit[0]]
            continue
        near = tree.query_nearest(pt, max_distance=NEAREST_MAX_DEG)
        if len(near):
            assign[o["id"]] = ids[near[0]]; snapped += 1
        else:
            outside += 1
    print(f"{len(assign)}/{len(obs)} observations tagged "
          f"({snapped} snapped from the coast, {outside} outside Canada's ecoregions)")

    # --- Simplify outlines for the web, keeping neighbouring borders identical ---
    simple = shapely.coverage_simplify(full, SIMPLIFY_DEG)
    features = []
    for rid, geom in zip(ids, simple):
        geom = shapely.set_precision(geom, 10 ** -DECIMALS)
        if geom.is_empty:
            geom = full[ids.index(rid)].simplify(SIMPLIFY_DEG)   # tiny islands can vanish
        props = dict(info[rid], zoneName=zone_names.get(info[rid]["zoneId"], ""))
        features.append({"type": "Feature", "properties": props, "geometry": mapping(geom)})

    with open(OUT_GEO, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, separators=(",", ":"))
    with open(OUT_OBS, "w") as f:
        json.dump(assign, f, separators=(",", ":"))
    print(f"Wrote {OUT_GEO} ({os.path.getsize(OUT_GEO)//1024} KB), "
          f"{OUT_OBS} ({os.path.getsize(OUT_OBS)//1024} KB)")


if __name__ == "__main__":
    main()
