"""
Build data/observations.json from the raw iNaturalist CSV export.

Usage (from the repo root):
    python3 scripts/build_observations.py

Re-run this whenever you download a fresh export from the BIMBY iNat project.
Update SRC below if the export folder/filename changes.
"""
import csv, json, os

SRC = "data/observations-782254.csv/observations-782254.csv"
OUT = "data/observations.json"

def main():
    rows = []
    with open(SRC, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            lat = r.get("latitude", "").strip()
            lng = r.get("longitude", "").strip()
            sci = r.get("scientific_name", "").strip()
            if not (lat and lng and sci):   # skip rows missing essentials
                continue
            rows.append({
                "id": int(r["id"]),
                "scientificName": sci,
                "commonName": r.get("common_name", "").strip(),
                "lat": round(float(lat), 5),   # ~1 m precision, smaller file
                "lng": round(float(lng), 5),
                "observedOn": r.get("observed_on", "").strip(),
            })
    with open(OUT, "w", encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, separators=(',', ':'))
    print(f"Wrote {len(rows)} observations -> {OUT} ({os.path.getsize(OUT)//1024} KB)")

if __name__ == "__main__":
    main()