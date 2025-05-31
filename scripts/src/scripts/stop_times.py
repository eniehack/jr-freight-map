import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta
import json
from typing import TypedDict
import geopandas
from shapely.geometry import LineString, Point
import shapely
from tqdm import tqdm

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

class ShapeItem(TypedDict):
    coord: tuple[float, float]
    timestamp: int | None
    seq: int
    stop: str | None

BASE_DATE = datetime.fromisoformat('2024-04-01')
BASE_TS = int(BASE_DATE.timestamp())

def parse_extended_time(base_date: datetime, time_str: str) -> datetime:
    h, m, s = map(int, time_str.split(":"))
    days, hour = divmod(h, 24)
    return base_date + timedelta(days=days, hours=hour, minutes=m, seconds=s)

def generate_stoptimesjson(conn: duckdb.DuckDBPyConnection) -> tuple[dict, list[StopTimeListItem]]:
    coords = conn.execute("SELECT s.stop_name, st_asgeojson(s.coord), s.stop_id FROM stops AS s;").fetchall()
    #stop_times = conn.execute("SELECT st.trip_id, st.arrival_time, st.departure_time, st_asgeojson(s.coord), st.stop_sequence, st.shape_id FROM stop_times;").fetchall()
    shapes = conn.execute("SELECT shape_id, st_asgeojson(coord),shape_pt_sequence FROM shapes;").fetchall()

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

    shapes_dict: defaultdict[str, list[ShapeItem]] = defaultdict(list)
    for row in shapes:
        coord = json.loads(row[1])
        shapes_dict[row[0]].append({
            "coord": coord['coordinates'],
            "timestamp": None,
            "seq": row[2],
            "stop": None,
        })
    for k, v in shapes_dict.items():
        shapes_dict[k] = sorted(v, key=lambda x: x['seq'])
    
    # 駅番号と到着時間をshapeの位置情報と繋ぎ合わせる
    for k, v in tqdm(shapes_dict.items(), "[shape_dict]", file=sys.stderr):
        for val in v:
            res = conn.execute(
                "SELECT s.stop_id, st.arrival_time, st.departure_time FROM trips t JOIN stop_times st ON st.trip_id = t.trip_id JOIN stops s ON s.stop_id = st.stop_id WHERE t.shape_id = ? AND s.coord = st_point(?, ?);",
                [k, val['coord'][0], val['coord'][1]]
            )
            row = res.fetchall()
            if len(row) < 1:
                continue
            row = row[-1]
            val["timestamp"] = int(parse_extended_time(BASE_DATE, row[2]).timestamp()) - BASE_TS if row[2] is not None else None
            val['stop'] = row[0]
    
    stoptime_dict: list[StopTimeListItem] = []
    for k, v in tqdm(shapes_dict.items(), "[stoptime_dict]", file=sys.stderr):
        times = []
        coords = []
        dept = v[0]['stop']
        dest = v[-1]['stop']
        for i in range(len(v)):
            times.append(v[i]["timestamp"])
            coords.append(v[i]["coord"])
        linestring = LineString(coords)
        gdf = geopandas.GeoDataFrame({
            "geometry": [Point(c) for c in coords],
            'timestamp': times,
        })
        gdf['distance'] = [linestring.project(p) for p in gdf['geometry']]
        gdf['timestamp'] = gdf['timestamp'].interpolate(method='linear')
        stoptime_dict.append(StopTimeListItem(ts=[int(ts) for ts in gdf['timestamp']], c=[tuple(p.coords[0]) for p in gdf['geometry']], dpt=dept, dst=dest))

    #collect_stoptime_dict: defaultdict[str, list[StopTimeValue]] = defaultdict(list)
    #for row in stop_times:
    #    stop_geom = json.loads(row[3])
    #    collect_stoptime_dict[row[0]].append({
    #        "arr": int(parse_extended_time(BASE_DATE, row[1]).timestamp()) - BASE_TS if row[1] is not None else None,
    #        "dept": int(parse_extended_time(BASE_DATE, row[2]).timestamp()) - BASE_TS if row[2] is not None else None,
    #        "coords": stop_geom['coordinates'],
    #        "seq": int(row[4]),
    #        "stop": row[5],
    #    })
    
    #stoptime_dict: list[StopTimeListItem] = []
    #for _, v in collect_stoptime_dict.items():
    #    times = []
    #    coords = []
    #    val = sorted(v, key=lambda x: x["seq"])
    #    dept = val[0]['stop']
    #    dest = val[-1]['stop']
    #    for i in range(len(val)):
    #        times.append(val[i]["arr"])
    #        coords.append(val[i]["coords"])
    #    linestring = LineString(coords)
    #    gdf = geopandas.GeoDataFrame({
    #        "geometry": [Point(c) for c in coords],
    #        'timestamp': times,
    #    })
    #    gdf['distance'] = [linestring.project(p) for p in gdf.geometry]
    #    gdf['timestamp'] = gdf['timestamp'].interpolate(method='linear')
    #    stoptime_dict.append(StopTimeListItem(ts=[int(ts) for ts in gdf['timestamp']], c=[tuple(p.coords[0]) for p in gdf['geometry']], dpt=dept, dst=dest))

    return (stop_geojson_root, stoptime_dict)
