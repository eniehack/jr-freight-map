import argparse
from pathlib import Path
import duckdb
import json

from src.scripts.shape import generate_shapejson
from src.scripts.stop_times import generate_stoptimesjson

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--gtfs_dir", "-i", type=Path)
    parser.add_argument("--output_dir", "-o", type=Path, default='.')
    args = parser.parse_args()

    conn = duckdb.connect()
    shapejson = generate_shapejson(conn, args.gtfs_dir / "shapes.txt")
    stopjson, stoptimesjson = generate_stoptimesjson(conn, args.gtfs_dir / "stops.txt", args.gtfs_dir / "stop_times.txt")

    with open(args.output_dir / 'shape.json', 'w') as f:
        json.dump(shapejson, f, ensure_ascii=False, separators=(',', ':'))

    with open(args.output_dir / 'stop.json', 'w') as f:
        json.dump(stopjson, f, ensure_ascii=False, separators=(',', ':'))

    with open(args.output_dir / 'stop_times.json', 'w') as f:
        json.dump(stoptimesjson, f, ensure_ascii=False, separators=(',', ':'))