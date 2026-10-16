"""
Build the postal code lookup used by the place search in index.html.

Only the first three characters of a postal code (the forward sortation area, FSA,
e.g. "V6T") are used: full six-character postal code locations are licensed by
Canada Post, but Statistics Canada publishes FSA boundaries under its Open Licence.

Input (downloaded manually from Statistics Canada, Census Forward Sortation Area
Boundary File, 2021, cartographic, shapefile, catalogue 92-179-X):
    data/raw/lfsa000b21a_e.zip
    https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/lfsa000b21a_e.zip

Output:
    data/postal-fsa.json   one entry per BC FSA (all start with "V"):
        "V6T": {"pt": [lat, lng], "km2": 12}
        "V0H": {"pt": [...], "km2": 9876, "wide": 1, "outline": <GeoJSON geometry>}
    "pt" is a point well inside the FSA's largest piece (where the page drops its pin).
    "wide" FSAs (rural codes, second character 0, or larger than WIDE_KM2) are too big
    for a pin to mean much, so the page shows their simplified "outline" instead and
    asks the visitor to click their spot.

Requires: pip install pyshp shapely pyproj

Run from the repo root:
    python3 scripts/build_postal.py
"""
import io
import json
import os
import zipfile

import shapefile                      # pyshp
import shapely
from pyproj import CRS, Geod, Transformer
import numpy as np
from shapely.geometry import MultiPolygon, shape, mapping
from shapely.ops import polylabel

ZIP = "data/raw/lfsa000b21a_e.zip"
OUT = os.environ.get("POSTAL_OUT", "data/postal-fsa.json")
BC_PRUID = "59"
WIDE_KM2 = 250           # FSAs bigger than this get an outline instead of a pin
OUTLINE_TOL = 0.02       # outline simplification (~2 km, as for the ecoregions)
MIN_PART_KM2 = 2         # drop islets smaller than this from outlines
DECIMALS = 3             # outline coordinate rounding (~100 m)


def read_zip_shapefile(zip_path):
    """Read the shapefile and its projection straight out of the zip."""
    with zipfile.ZipFile(zip_path) as z:
        names = {os.path.splitext(n)[1].lower(): n for n in z.namelist()}
        parts = {ext: io.BytesIO(z.read(names[ext])) for ext in (".shp", ".shx", ".dbf")}
        prj = z.read(names[".prj"]).decode("latin1")
    reader = shapefile.Reader(shp=parts[".shp"], shx=parts[".shx"], dbf=parts[".dbf"], encoding="latin1")
    return reader, prj


def main():
    reader, prj = read_zip_shapefile(ZIP)
    tr = Transformer.from_crs(CRS.from_wkt(prj), "EPSG:4326", always_xy=True)
    to_ll = lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1]))
    geod = Geod(ellps="GRS80")

    out = {}
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        if str(rec["PRUID"]) != BC_PRUID:
            continue
        fsa = rec["CFSAUID"].strip().upper()
        geom = shapely.transform(shape(sr.shape.__geo_interface__), to_ll).buffer(0)
        km2 = abs(geod.geometry_area_perimeter(geom)[0]) / 1e6
        largest = max(getattr(geom, "geoms", [geom]), key=lambda g: g.area)
        pt = polylabel(largest, tolerance=0.0005)
        entry = {"pt": [round(pt.y, 4), round(pt.x, 4)], "km2": round(km2)}
        if fsa[1] == "0" or km2 > WIDE_KM2:
            parts = [g for g in getattr(geom, "geoms", [geom])
                     if abs(geod.geometry_area_perimeter(g)[0]) / 1e6 >= MIN_PART_KM2] or [largest]
            outline = MultiPolygon(parts).simplify(OUTLINE_TOL, preserve_topology=True)
            outline = shapely.set_precision(outline, 10 ** -DECIMALS)
            entry["wide"] = 1
            entry["outline"] = mapping(outline)
        out[fsa] = entry

    doc = {
        "source": "Statistics Canada, Census Forward Sortation Area Boundary File, 2021 "
                  "(92-179-X). Contains information licensed under the Open Government "
                  "Licence – Canada / Statistics Canada Open Licence.",
        "fsa": dict(sorted(out.items())),
    }
    with open(OUT, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    wide = sum(1 for e in out.values() if e.get("wide"))
    print(f"{len(out)} BC FSAs ({wide} wide). Wrote {OUT} ({os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    main()
