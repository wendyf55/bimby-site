"""
Build the ecoregion data used by index.html.

Inputs (downloaded manually from AAFC's National Ecological Framework for Canada,
https://sis.agr.gc.ca/cansis/nsdb/ecostrat/gis_data.html):
    data/raw/ecoregion_shp.zip   194 ecoregions (218 polygons), NAD83 lat/long
    data/raw/ecozone_shp.zip     15 ecozones (used for zone names only)
    data/observations.json       built by scripts/build_observations.py

Outputs:
    data/ecoregions.geojson             simplified ecoregion outlines for the map; the
                                        source builders tag each record's ecoregion
                                        with these (scripts/source_files.py)
    data/ecozones.geojson               ecozone outlines (merged from the simplified
                                        ecoregions); not used by any page right now

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
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

RAW = "data/raw"
OUT_GEO = "data/ecoregions.geojson"
OUT_ZONES = "data/ecozones.geojson"

SIMPLIFY_DEG = 0.02      # coverage-simplify tolerance (~2 km); shared borders stay shared
DECIMALS = 3             # coordinate rounding in the output (~100 m)

# Tidy a few inconsistent names in the 2003 ecozone attribute table
ZONE_NAME_FIXES = {"Boreal PLain": "Boreal Plain", "MixedWood Plain": "Mixedwood Plain"}

# The 2006 ecoregion table uses the US spelling "Okanogan" for the two cross-border
# regions (210 Okanogan Range, 211 Okanogan Highland); use the Canadian "Okanagan"
# so they match the rest of the site. This departs from the official AAFC names.
def fix_region_name(name):
    return name.replace("Okanogan", "Okanagan")


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
        info[rid] = {"id": rid, "name": fix_region_name(sr.record["REGION_NAM"].strip()),
                     "nameFr": fix_region_name(sr.record["REGION_NOM"].strip()), "zoneId": sr.record["ECOZONE"]}
    ids = sorted(parts)
    full = [unary_union(parts[i]) for i in ids]
    print(f"{len(ids)} ecoregions across {len(zone_names)} ecozones")

    # --- Simplify outlines for the web, keeping neighbouring borders identical ---
    simple = shapely.coverage_simplify(full, SIMPLIFY_DEG)
    features, zone_parts = [], {}
    for rid, geom in zip(ids, simple):
        geom = shapely.set_precision(geom, 10 ** -DECIMALS)
        if geom.is_empty:
            geom = full[ids.index(rid)].simplify(SIMPLIFY_DEG)   # tiny islands can vanish
        props = dict(info[rid], zoneName=zone_names.get(info[rid]["zoneId"], ""))
        features.append({"type": "Feature", "properties": props, "geometry": mapping(geom)})
        zone_parts.setdefault(info[rid]["zoneId"], []).append(geom)

    # --- Ecozone outlines: merge each zone's simplified ecoregions ---
    zone_features = []
    for zid in sorted(zone_parts):
        geom = shapely.set_precision(unary_union(zone_parts[zid]), 10 ** -DECIMALS)
        zone_features.append({"type": "Feature",
                              "properties": {"id": zid, "name": zone_names.get(zid, "")},
                              "geometry": mapping(geom)})

    with open(OUT_GEO, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, separators=(",", ":"))
    with open(OUT_ZONES, "w") as f:
        json.dump({"type": "FeatureCollection", "features": zone_features}, f, separators=(",", ":"))
    print(f"Wrote {OUT_ZONES} ({os.path.getsize(OUT_ZONES)//1024} KB)")
    print(f"Wrote {OUT_GEO} ({os.path.getsize(OUT_GEO)//1024} KB)")
    print("If the outlines changed, rebuild the sources so records are re-tagged:\n"
          "    python3 scripts/build_observations.py && python3 scripts/build_inat.py")


if __name__ == "__main__":
    main()
