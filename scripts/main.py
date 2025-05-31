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
    conn.install_extension("spatial")
    conn.load_extension("spatial")
    conn.execute("CREATE TABLE stop_times AS SELECT trip_id, arrival_time, departure_time, stop_id, stop_sequence FROM read_csv(?, header=true);", [str(args.gtfs_dir / "stop_times.txt")])
    conn.execute("CREATE TABLE stops AS SELECT stop_id, stop_code, stop_name, st_point(stop_lon,stop_lat) as coord FROM read_csv(?, header=true);", [str(args.gtfs_dir / "stops.txt")])
    conn.execute("CREATE TABLE trips AS SELECT route_id, trip_id, shape_id FROM read_csv(?, header=True);", [str(args.gtfs_dir / "trips.txt")])
    conn.execute("CREATE TABLE shapes AS SELECT shape_id, shape_pt_sequence, st_point(shape_pt_lon, shape_pt_lat) as coord FROM read_csv(?, header=true);", [str(args.gtfs_dir / "shapes.txt")])
    #shapejson = generate_shapejson(conn)
    stopjson, stoptimesjson = generate_stoptimesjson(conn)

    #with open(args.output_dir / 'shape.json', 'w') as f:
    #    json.dump(shapejson, f, ensure_ascii=False, separators=(',', ':'))

    with open(args.output_dir / 'stop.json', 'w') as f:
        json.dump(stopjson, f, ensure_ascii=False, separators=(',', ':'))

    with open(args.output_dir / 'stop_times.json', 'w') as f:
        json.dump(stoptimesjson, f, ensure_ascii=False, separators=(',', ':'))