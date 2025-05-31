import json
import argparse
from pathlib import Path
import duckdb

def generate_shapejson(conn: duckdb.DuckDBPyConnection) -> dict:
    shapes = conn.execute("SELECT shape_id, st_asgeojson(line) FROM shapes;").fetchall()

    geojson_root = {"type": "FeatureCollection", "features": []}
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
    return geojson_root


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", type=Path, default="./shape.txt")
    parser.add_argument("--output", "-o", type=Path, default='./shape.json')
    args = parser.parse_args()

    conn = duckdb.connect()
    geojson = generate_shapejson(conn, args.input)

    with open(args.output, 'w') as f:
        json.dump(geojson, f)