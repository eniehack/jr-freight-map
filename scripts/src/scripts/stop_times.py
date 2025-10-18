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
import pandas as pd

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

# (0,0)を無効値として扱う補完関数
def interpolate_coords_with_sentinel(df, sentinel_coord=(0, 0)):
    # (0,0)をNaNに置き換えて補完
    coords_df = pd.DataFrame([
        {'lon': p.x if (p.x, p.y) != sentinel_coord else None,
         'lat': p.y if (p.x, p.y) != sentinel_coord else None}
        for p in df.geometry
    ])
    
    # 線形補完
    coords_df = coords_df.interpolate(method='linear')
    
    # 補完後の座標でGeometryを再作成
    return [Point(row.lon, row.lat) for row in coords_df.itertuples()]

def get_boundary_timestamps(min_ts: int, max_ts: int) -> tuple[list[int], list[int]]:
    """運行時間範囲内の日境界タイムスタンプを取得"""
    boundaries = [86400, 172800, 259200, 345600]  # 24h, 48h, 72h, 96h
    after_boundaries = [b for b in boundaries if min_ts < b < max_ts]
    before_boundaries = []
    for boundary in after_boundaries:
        before_boundaries.append(boundary - 1)
    return before_boundaries, after_boundaries

def generate_stop_geojson(conn: duckdb.DuckDBPyConnection) -> dict:
    coords = conn.execute("SELECT s.stop_name, st_asgeojson(s.coord), s.stop_id FROM stops AS s;").fetchall()
    stop_geojson_root = {"type": "FeatureCollection", "features": []}
    for s in coords:
        geom = load_str_as_geojson(s[1])
        geojson = {
            'type': 'Feature',
            'geometry': geom,
            'properties': {
                'name': s[0],
                'id': s[2]
            }
        }
        stop_geojson_root['features'].append(geojson)
    return stop_geojson_root

def generate_stoptimesjson(conn: duckdb.DuckDBPyConnection) -> list[StopTimeListItem]:
    #stop_times = conn.execute("SELECT st.trip_id, st.arrival_time, st.departure_time, st_asgeojson(s.coord), st.stop_sequence, st.shape_id FROM stop_times;").fetchall()
    shapes = conn.execute("SELECT shape_id, st_asgeojson(coord), shape_pt_sequence FROM shapes;").fetchall()

    shapes_dict: defaultdict[str, list[ShapeItem]] = defaultdict(list)
    for row in shapes:
        coord = load_str_as_geojson(row[1])
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
                "SELECT s.stop_name, st.arrival_time, st.departure_time FROM trips t JOIN stop_times st ON st.trip_id = t.trip_id JOIN stops s ON s.stop_id = st.stop_id WHERE t.shape_id = ? AND s.coord = st_point(?, ?);",
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
        max_ts = max(gdf['timestamp'])
        min_ts = min(gdf['timestamp'])
        # after_boundaryは24時間ごとに分割したときの24:00に該当する秒数がlistになって入ってｔいる
        # before_boundaryはafter_boundaryの1秒前がlistになって入ってｔいる。これはboundaryによってPointと時刻が24:00ごとに分割する際に23:59まで点を表示させるため
        before_boundaries, after_boundaries = get_boundary_timestamps(min_ts, max_ts)
        after_boundary_gdf = geopandas.GeoDataFrame({
            "geometry": [Point(0, 0)] * len(after_boundaries),
            'timestamp': after_boundaries,
        })
        before_boundary_gdf = geopandas.GeoDataFrame({
            "geometry": [Point(0, 0)] * len(before_boundaries),
            'timestamp': before_boundaries,
        })
        merged_gdf = pd.concat([gdf, after_boundary_gdf, before_boundary_gdf]).sort_values('timestamp')
        merged_gdf['geometry'] = interpolate_coords_with_sentinel(merged_gdf)
        splitted_gdf = merged_gdf[merged_gdf['timestamp'] < 86400]
        if len( splitted_gdf ) != 0:
            stoptime_dict.append(StopTimeListItem(ts=[int(ts) for ts in splitted_gdf['timestamp']], c=[tuple(p.coords[0]) for p in splitted_gdf['geometry']], dpt=dept, dst=dest))
        if 1 <= len(after_boundaries):
            for boundary in after_boundaries:
                splitted_gdf = merged_gdf[boundary <= merged_gdf['timestamp']]
                if 1 <= len(splitted_gdf):
                    splitted_gdf.loc[:, 'timestamp'] = splitted_gdf['timestamp'] % boundary
                    stoptime_dict.append(StopTimeListItem(ts=[int(ts) for ts in splitted_gdf['timestamp']], c=[tuple(p.coords[0]) for p in splitted_gdf['geometry']], dpt=dept, dst=dest))
def load_str_as_geojson(s: str) -> dict:
    return json.loads(s)

