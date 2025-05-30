import json
import argparse
from pathlib import Path
import duckdb

def generate_shapejson(conn: duckdb.DuckDBPyConnection, shapes_txt_path: Path) -> dict:
    conn.install_extension("spatial")
    conn.load_extension("spatial")
    conn.execute("CREATE TABLE shapes_raw AS SELECT shape_id, shape_pt_sequence, st_point(shape_pt_lon, shape_pt_lat) as point FROM read_csv(?, header=true);", [str(shapes_txt_path)])
    conn.execute("CREATE TABLE shapes AS SELECT shape_id, st_makeline(list(point ORDER BY shape_pt_sequence ASC)) as line FROM shapes_raw GROUP BY shape_id;")
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