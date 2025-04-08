import json
import csv
import argparse
from pathlib import Path
import sys

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gtfs_dir", type=Path)
    args = parser.parse_args()
    geojson_root = {"type": "FeatureCollection", "features": []}
    with open(args.gtfs_dir / "stops.txt") as f:
        reader = csv.DictReader(f)
        for row in reader:
            geojson_root["features"].append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["stop_lon"]), float(row["stop_lat"])],
                },
                "properties": {
                    "name": row["stop_name"],
                    "id": row["stop_id"]
                }
            })
    json.dump(geojson_root, sys.stdout, ensure_ascii=False)
