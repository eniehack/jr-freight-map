import json
import csv
import argparse
from pathlib import Path
import sys
from dataclasses import dataclass
import duckdb

@dataclass
class Trip:
    id: str
    arrival: str | None
    dept: str | None
    station_id: str

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gtfs_dir", "-i", type=Path)
    parser.add_argument("--output_dir", "-o", type=Path, default='.')
    args = parser.parse_args()
    geojson_root = {"type": "FeatureCollection", "features": []}

    conn = duckdb.connect()
    conn.install_extension("spatial")
    conn.load_extension("spatial")
    conn.execute("CREATE TABLE shapes_raw AS SELECT shape_id, shape_pt_sequence, st_point(shape_pt_lon, shape_pt_lat) as point FROM read_csv(?, header=true);", [str(args.gtfs_dir / "shapes.txt")])
    conn.execute("CREATE TABLE shapes AS SELECT shape_id, st_makeline(list(point ORDER BY shape_pt_sequence ASC)) as line FROM shapes_raw GROUP BY shape_id;")
    shapes = conn.execute("SELECT shape_id, st_asgeojson(line) FROM shapes;").fetchall()
    for shape in shapes:
        geom = json.loads(shape[1])
        geojson = {
            'type': 'Feature',
            'geometry': geom,
            'property': {
                'shape_id': shape[0]
            }
        }
        geojson_root['features'].append(geojson)

    with open(args.output_dir / 'shapes.json', 'w') as f:
        json.dump(geojson_root, f)