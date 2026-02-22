import sys
from collections import defaultdict, deque
from pathlib import Path
from datetime import datetime, timedelta
import json
from typing import TypedDict
import geopandas
import shapely
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
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
    id: str
    ts: list[int] # timestamp
    c: list[tuple[float, float]]
    dpt: str
    dst: str

class ShapeItem(TypedDict):
    coord: str
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
    shapes_dict: defaultdict[str, list[ShapeItem]] = defaultdict(list)
    total_shapes = conn.execute("SELECT COUNT(DISTINCT shape_id) FROM shapes").fetchone() # tqdmで進捗率を出すためにshapeの数を数えておく
    # shapeには被っている部分がある（e.g.東京-北旭川は途中まで東京-札幌の一部として運行される）ため、被っている部分をmerge（片寄せ）する処理
    with tqdm(total=total_shapes[0], desc="[merging shapes]", file=sys.stderr) as pbar:
        root_shapes: list[tuple[str, int]] = conn.execute(
            """
            SELECT DISTINCT component_shape_id, seq
            FROM composite_shapes
            WHERE REGEXP_MATCHES(component_shape_id, '^\\d+_\\d+_\\d+$');
            """).fetchall()
        shapes_stack: deque[tuple[str, str, int]] = deque() # idと親のid,親の最後のseqのtuple
        for root_shape_id, _ in root_shapes:
            shps: list[tuple[str, int]] = conn.execute(
                "SELECT st_astext(coord), shape_pt_sequence FROM shapes WHERE shape_id = ? ORDER BY shape_pt_sequence;",
                [root_shape_id]
            ).fetchall()
            for sh in shps:
                shapes_dict[root_shape_id].append({
                    "coord": sh[0],
                    "seq": sh[1],
                    "timestamp": None,
                    "stop": None,
                })
            children = conn.execute(
                """
                SELECT DISTINCT shape_id
                FROM composite_shapes
                WHERE REGEXP_MATCHES(shape_id, '^' || ? || '_\\d+_\\d+$');
                """,
                [root_shape_id]
            ).fetchall()
            for child in children:
                shapes_stack.append((child[0], root_shape_id, shps[-1][1]))
            pbar.update(1) # whileを使うと自動でやってくれないのでtqdmの進捗率を更新する

        while 0 < len(shapes_stack):
            current_shape_id, parent_shape_id, parent_shape_last_seq_index = shapes_stack.pop()
            splitted_shape: list[tuple[str, int]] = conn.execute(
                """
                SELECT st_astext(coord), shape_pt_sequence
                FROM shapes
                WHERE shape_id = ?
                  AND ? <= shape_pt_sequence
                ORDER BY shape_pt_sequence;
                """,
                [current_shape_id, parent_shape_last_seq_index]
            ).fetchall()
            for sh in splitted_shape:
                shapes_dict[current_shape_id].append({
                    "coord": sh[0],
                    "seq": sh[1],
                    "timestamp": None,
                    "stop": None,
                })

            if 0 < len(splitted_shape):
                children: list[tuple[str]] = conn.execute(
                    "SELECT DISTINCT shape_id FROM composite_shapes WHERE REGEXP_MATCHES(shape_id, '^' || ? || '_\\d+_\\d+$');",
                    [current_shape_id]
                ).fetchall()
                for child in children:
                    child_shape_id = child[0]
                    shapes_stack.append((child_shape_id, current_shape_id, splitted_shape[-1][1]))
            pbar.update(1)
    print(shapes_dict)

    # 駅番号と到着時間をshapeの位置情報と繋ぎ合わせる
    for k, v in tqdm(shapes_dict.items(), "[shape_dict]", file=sys.stderr):
        for val in v:
            row = conn.execute(
                """
                SELECT s.stop_name, st.arrival_time, st.departure_time
                FROM trips t 
                JOIN stop_times st
                  ON st.trip_id = t.trip_id
                JOIN stops s ON s.stop_id = st.stop_id
                WHERE t.shape_id = ?
                  AND s.coord = st_geomfromtext(?);
                """,
                [k, val['coord']]
            ).fetchall()
            if len(row) < 1:
                continue
            row = row[-1]
            val["timestamp"] = int(parse_extended_time(BASE_DATE, row[2]).timestamp()) - BASE_TS if row[2] is not None else None
            val['stop'] = row[0]
    print(shapes_dict)
    
    stoptime_dict: list[StopTimeListItem] = []
    for k, l in tqdm(shapes_dict.items(), "[stoptime_dict]", file=sys.stderr):
        times = []
        coords: list[BaseGeometry] = []
        dept = l[0]['stop']
        dest = l[-1]['stop']
        for i in range(len(l)):
            times.append(l[i]["timestamp"])
            coords.append(shapely.from_wkt(l[i]["coord"]))
        linestring = LineString(coords)
        gdf = geopandas.GeoDataFrame({
            "geometry": coords,
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
            stoptime_dict.append(StopTimeListItem(id=k, ts=[int(ts) for ts in splitted_gdf['timestamp']], c=[tuple(p.coords[0]) for p in splitted_gdf['geometry']], dpt=dept, dst=dest))
        if 1 <= len(after_boundaries):
            for boundary in after_boundaries:
                splitted_gdf = merged_gdf[boundary <= merged_gdf['timestamp']]
                if 1 <= len(splitted_gdf):
                    splitted_gdf.loc[:, 'timestamp'] = splitted_gdf['timestamp'] % boundary
                    stoptime_dict.append(StopTimeListItem(id=k, ts=[int(ts) for ts in splitted_gdf['timestamp']], c=[tuple(p.coords[0]) for p in splitted_gdf['geometry']], dpt=dept, dst=dest))
    return stoptime_dict

class Station(TypedDict):
    id: str
    code: str
    name: str
    stop_seq: int

def get_stop_stations_from_shapeid(conn: duckdb.DuckDBPyConnection, shape: str) -> list[Station]:
    stations = conn.execute(
        "SELECT s.stop_id, s.stop_code, s.stop_name, st.stop_sequence FROM trips t JOIN stop_times st ON st.trip_id = t.trip_id JOIN stops s ON s.stop_id = st.stop_id WHERE t.shape_id = ? ORDER BY st.stop_sequence ASC",
        (shape,)
    ).fetchall()
    return [{"id": s[0], "code": s[1], "name": s[2], "stop_seq": s[3]} for s in stations]

def make_shape_geodataframe(conn: duckdb.DuckDBPyConnection, shape_id: str) -> geopandas.GeoDataFrame:
    """shapeを構成する点1つ1つをGeoJSONのFeatureとして作成し、構成点たちをGeoDataFrameに入れて返す
    """
    features = make_shape_point_geojson(conn, shape_id)
    return geopandas.GeoDataFrame.from_features(features)

def make_shape_point_geojson(conn: duckdb.DuckDBPyConnection, shape_id: str) -> list:
    """shapeを構成する点1つ1つをGeoJSONのFeatureとして作成し、構成点たちをFeatureのlistとして返す。duckdbからデータを取り出してgeodataframeを生成する場合のヘルパとして使える
    """
    shape_points_result = conn.execute(
        "SELECT shape_id, st_asgeojson(coord) as coord, shape_pt_sequence FROM shapes WHERE shape_id = ?", (shape_id,)).fetchall()
    features = []
    for point in shape_points_result:
        coord = load_str_as_geojson(point[1])
        feature = {
            "geometry": coord,
            "properties": {"shape_id": point[0], "seq": point[2]},
            "type": "Feature"
        }
        features.append(feature)
    return features

def merge_duplicated_subshape(base_df: pd.DataFrame, df2: pd.DataFrame):
    """JR貨物のshapeには部分集合を含む場合があり（時刻表上ではA-B間の列車とされているが、実際には途中までA-C間の列車に連結されて輸送され、C-B間は独立して運行される場合がある）、部分集合として別の異なるshapeが合致するものを1つのdataframeに統合する。異なるshapeは既に判明しているものとする
    """
    return df2.combine_first(base_df)

def load_str_as_geojson(s: str) -> dict:
    return json.loads(s)

def find_subset_shape(conn: duckdb.DuckDBPyConnection, shape_id: str) -> list[str]:
    """JR貨物のshapeには部分集合を含む場合があり（時刻表上ではA-B間の列車とされているが、実際には途中までA-C間の列車に連結されて輸送され、C-B間は独立して運行される場合がある）、部分集合として別の異なるshapeで条件に合致するものをlistにして返す
    """
    splitted_id = shape_id.split("_")
    splitted_id_len = len(splitted_id)
    short_shape_ids = []
    for l in range(splitted_id_len, 2, -2):
        if l == splitted_id_len: continue
        short_shapes = conn.execute("SELECT shape_id FROM shapes WHERE shape_pt_sequence = 1 AND shape_id = ?", ('_'.join(splitted_id[:l]),)).fetchall()
        if short_shapes is not None:
            for sh in short_shapes:
                short_shape_ids.append(sh[0])
    return short_shape_ids