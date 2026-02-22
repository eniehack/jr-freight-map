import argparse
from pathlib import Path
import duckdb
import json
import os
from collections import deque

from src.scripts.shape import generate_shapejson
from src.scripts.stop_times import generate_stoptimesjson, generate_stop_geojson

def insert_composite_shapes(conn: duckdb.DuckDBPyConnection):
    root_shapes = conn.execute(r"SELECT DISTINCT shape_id FROM shapes WHERE REGEXP_MATCHES(shape_id, '^\d+_\d+_\d+$');").fetchall()
    root_shapes_set: set[str] = {s[0] for s in root_shapes}
    # DFSを使って shape_idの部分文字列を探索する
    shape_stack: deque[tuple[str, list[str]]] = deque([(s, []) for s in root_shapes_set])
    while 0 < len(shape_stack):
        current = shape_stack.pop()
        shape_id, shape_parent = current[0], current[1]
        args: list[tuple[str, str, int]] = []
        for i, parent in enumerate(shape_parent):
            args.append((shape_id, parent, i + 1))
        args.append((shape_id, shape_id, len(shape_parent)+1))
        conn.executemany("INSERT INTO composite_shapes VALUES (?, ?, ?)", args)
        child_shapes: list[tuple[str]] = conn.execute("SELECT DISTINCT shape_id FROM shapes WHERE REGEXP_MATCHES(shape_id, '^' || ? ||'_\\d+_\\d+$');", [shape_id]).fetchall()
        parents = shape_parent + [shape_id]
        shape_stack.extend([(c[0], parents) for c in child_shapes])

def create_db(conn: duckdb.DuckDBPyConnection):
    conn.execute("CREATE TABLE stop_times AS SELECT trip_id, arrival_time, departure_time, stop_id, stop_sequence FROM read_csv(?, header=true);", [str(args.gtfs_dir / "stop_times.txt")])
    conn.execute("CREATE TABLE stops AS SELECT stop_id, stop_code, stop_name, st_point(stop_lon,stop_lat) as coord FROM read_csv(?, header=true);", [str(args.gtfs_dir / "stops.txt")])
    conn.execute("CREATE TABLE trips AS SELECT route_id, trip_id, shape_id FROM read_csv(?, header=True);", [str(args.gtfs_dir / "trips.txt")])
    conn.execute("CREATE TABLE shapes AS SELECT shape_id, shape_pt_sequence, st_point(shape_pt_lon, shape_pt_lat) as coord FROM read_csv(?, header=true);", [str(args.gtfs_dir / "shapes.txt")])
    conn.execute("""
        CREATE TABLE composite_shapes (
            shape_id VARCHAR,
            component_shape_id VARCHAR,
            seq INTEGER,
            PRIMARY KEY (shape_id, seq)
        )
    """)
    insert_composite_shapes(conn)

def restore_db(conn: duckdb.DuckDBPyConnection, db_dir: Path):
    conn.execute(f"IMPORT DATABASE \'{db_dir}\';")

def save_db(conn: duckdb.DuckDBPyConnection, db_dir: Path):
    conn.execute(f"EXPORT DATABASE \'{db_dir}\';")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--gtfs_dir", "-i", type=Path)
    parser.add_argument("--output_dir", "-o", type=Path, default='.')
    parser.add_argument("--db_dir", "-db", type=Path, default=None)
    parser.add_argument("--persistent", action='store_true')
    args = parser.parse_args()

    conn = duckdb.connect()
    conn.install_extension("spatial")
    conn.load_extension("spatial")
    db_dir_len = len(os.listdir(args.db_dir))
    if 1 < db_dir_len and args.db_dir is not None:
        restore_db(conn, args.db_dir)
    elif db_dir_len < 1 and args.db_dir is not None:
        create_db(conn)
        if args.persistent:
            save_db(conn, args.db_dir)
    print("generated composite_shapes")
    #shapejson = generate_shapejson(conn)
    stoptimesjson = generate_stoptimesjson(conn)
    stopgeojson = generate_stop_geojson(conn)

    #with open(args.output_dir / 'shape.json', 'w') as f:
    #    json.dump(shapejson, f, ensure_ascii=False, separators=(',', ':'))

    with open(args.output_dir / 'stop.json', 'w') as f:
        json.dump(stopgeojson, f, ensure_ascii=False, separators=(',', ':'))

    with open(args.output_dir / 'stop_times.json', 'w') as f:
        json.dump(stoptimesjson, f, ensure_ascii=False, separators=(',', ':'))