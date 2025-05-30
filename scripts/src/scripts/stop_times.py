import csv
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta
import json
from typing import TypedDict
import geopandas
from shapely.geometry import LineString, Point

import duckdb

class StopTimeValue(TypedDict):
    arr: int | None
    dept: int | None
    coords: tuple[float, float]
    stop: str
    seq: int

class StopTimeListItem(TypedDict):
    ts: list[int] # timestamp
    c: list[tuple[float, float]]
    dpt: str
    dst: str

BASE_DATE = datetime.fromisoformat('2024-04-01')
BASE_TS = int(BASE_DATE.timestamp())

def parse_extended_time(base_date: datetime, time_str: str) -> datetime:
    h, m, s = map(int, time_str.split(":"))
    days, hour = divmod(h, 24)
    return base_date + timedelta(days=days, hours=hour, minutes=m, seconds=s)

def generate_stoptimesjson(conn: duckdb.DuckDBPyConnection, stops_txt_path: Path, stoptimes_txt_path: Path) -> tuple[dict, list[StopTimeListItem]]:
    conn.install_extension("spatial")
    conn.load_extension("spatial")
    conn.execute("CREATE TABLE stop_times AS SELECT trip_id, arrival_time, departure_time, stop_id, stop_sequence FROM read_csv(?, header=true);", [str(stoptimes_txt_path)])
    conn.execute("CREATE TABLE stops AS SELECT stop_id, stop_code, stop_name, st_point(stop_lon,stop_lat) as coord FROM read_csv(?, header=true);", [str(stops_txt_path)])
    coords = conn.execute("SELECT s.stop_name, st_asgeojson(s.coord), s.stop_id FROM stops AS s;").fetchall()
    stop_times = conn.execute("SELECT st.trip_id, st.arrival_time, st.departure_time, st_asgeojson(s.coord), st.stop_sequence, s.stop_name FROM stop_times AS st JOIN stops AS s ON s.stop_id = st.stop_id;").fetchall()

    stop_geojson_root = {"type": "FeatureCollection", "features": []}
    for s in coords:
        geom = json.loads(s[1])
        geojson = {
            'type': 'Feature',
            'geometry': geom,
            'property': {
                'name': s[0],
                'id': s[2]
            }
        }
        stop_geojson_root['features'].append(geojson)

    collect_stoptime_dict: defaultdict[str, list[StopTimeValue]] = defaultdict(list)
    for row in stop_times:
        stop_geom = json.loads(row[3])
        collect_stoptime_dict[row[0]].append({
            "arr": int(parse_extended_time(BASE_DATE, row[1]).timestamp()) - BASE_TS if row[1] is not None else None,
            "dept": int(parse_extended_time(BASE_DATE, row[2]).timestamp()) - BASE_TS if row[2] is not None else None,
            "coords": stop_geom['coordinates'],
            "seq": int(row[4]),
            "stop": row[5],
        })
    
    stoptime_dict: list[StopTimeListItem] = []
    for _, v in collect_stoptime_dict.items():
        times = []
        coords = []
        val = sorted(v, key=lambda x: x["seq"])
        dept = val[0]['stop']
        dest = val[-1]['stop']
        for i in range(len(val)):
            times.append(val[i]["arr"])
            coords.append(val[i]["coords"])
        linestring = LineString(coords)
        gdf = geopandas.GeoDataFrame({
            "geometry": [Point(c) for c in coords],
            'timestamp': times,
        })
        gdf['distance'] = [linestring.project(p) for p in gdf.geometry]
        gdf['timestamp'] = gdf['timestamp'].interpolate(method='linear')
        stoptime_dict.append(StopTimeListItem(ts=[int(ts) for ts in gdf['timestamp']], c=[tuple(p.coords[0]) for p in gdf['geometry']], dpt=dept, dst=dest))

    return (stop_geojson_root, stoptime_dict)
