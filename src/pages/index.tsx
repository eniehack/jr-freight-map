import {
  MapViewState,
  DeckProps,
  LayersList,
  PickingInfo,
} from "@deck.gl/core";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { Map, useControl } from "react-map-gl/maplibre";
import { GeoJsonLayer } from "@deck.gl/layers";
import { TripsLayer } from "@deck.gl/geo-layers";
import type { Feature, FeatureCollection, Point, LineString } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useMemo, useState } from "react";

const INITIAL_VIEW_STATE: MapViewState = {
  longitude: 139.80034,
  latitude: 35.73272,
  zoom: 13,
};

const DeckGLOverlay = (props: DeckProps) => {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props));
  overlay.setProps(props);
  return null;
};

type StopGeoJsonProp = {
  stop_id: string;
  stop_name: string;
  route_ids: string[];
};

type ShapeGeoJsonProp = {
  shape_id: string;
};

type StopTimesJson = {
  ts: number[];
  c: [number, number][];
  dpt: string;
  dst: string;
};

export default function Home() {
  const [timestamp, setTimestamp] = useState<number>(40200);

  const getTooltip = useCallback(({ object }: PickingInfo<StopTimesJson>) => {
    return object ? `${object.dpt} - ${object.dst}` : null;
  }, []);

  const layers = useMemo<LayersList>(() => {
    const layerArr = [];

    /*
    layerArr.push(
      new GeoJsonLayer<ShapeGeoJsonProp>({
        id: "routes",
        data: "/data/shapes.json",
        getText: (d) => d.properties.shape_id,
        getTextColor: [0xff, 0xff, 0xff],
        pickable: true,
        stroked: true,
        filled: false,
        lineWidthScale: 20,
        lineWidthMinPixels: 3,
        lineWidthMaxPixels: 3,
        getLineColor: [255, 0, 0], // 赤色の線
        getLineWidth: 2,
      }),
    );
    */

    layerArr.push(
      new GeoJsonLayer<StopGeoJsonProp>({
        id: "station",
        data: "/data/stops.json",
        pointType: "circle+text",
        getText: (f: Feature<Point, StopGeoJsonProp>) => f.properties.stop_name,
        textCharacterSet: "auto",
        textFontFamily: "Noto Sans JP",
        getTextSize: 16,
        getTextPixelOffset: [0, -3],
        getTextAlignmentBaseline: "bottom",
        getPointRadius: 4,
        pointRadiusMaxPixels: 5,
        pointRadiusMinPixels: 5,
        filled: true,
        getFillColor: [0xff, 0xff, 0xff],
        getTextColor: [0xff, 0xff, 0xff],
      }),
    );

    layerArr.push(
      new TripsLayer<StopTimesJson>({
        id: "trips",
        data: "/data/stop_times.json",
        getPath: (d: StopTimesJson) => d.c,
        getTimestamps: (d: StopTimesJson) => d.ts,
        opacity: 0.6,
        widthMinPixels: 6,
        getColor: [0x8a, 0x58, 0x87],
        currentTime: timestamp,
        trailLength: 600,
        capRounded: true,
        jointRounded: true,
        pickable: true,
      }),
    );

    return layerArr;
  }, [timestamp]);

  useEffect(() => {
    const timer = setInterval(() => {
      setTimestamp((prev) => prev + 1);
    }, 200);

    return () => clearInterval(timer);
  }, []);

  return (
    <main className="absolute h-full w-full top-0 left-0">
      <p>{timestamp}</p>
      <Map
        initialViewState={INITIAL_VIEW_STATE}
        //mapStyle="https://tile.openstreetmap.jp/styles/osm-bright-ja/style.json"
        mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
        reuseMaps
        id="map"
      >
        <DeckGLOverlay controller layers={layers} getTooltip={getTooltip} />
      </Map>
    </main>
  );
}
