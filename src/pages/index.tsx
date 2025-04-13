import { MapViewState, DeckProps, LayersList } from "@deck.gl/core";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { Map, useControl } from "react-map-gl/maplibre";
import { GeoJsonLayer } from "@deck.gl/layers";
import type { Feature, FeatureCollection, Point, LineString } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useState } from "react";

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

export default function Home() {
  const [stops, setStops] = useState<null | FeatureCollection<
    Point,
    StopGeoJsonProp
  >>(null);
  const [routes, setRoutes] = useState<null | FeatureCollection<
    LineString,
    { shape_id: string }
  >>(null);

  const layers = useMemo<LayersList>(() => {
    const layerArr = [];
    if (stops === null || routes === null) {
      return [];
    }

    layerArr.push(
      new GeoJsonLayer<{ shape_id: string }>({
        id: "routes",
        data: routes,
        getText: (d) => d.properties.shape_id,
        getTextColor: [0xff, 0xff, 0xff],
        pickable: true,
        stroked: true,
        filled: false,
        lineWidthScale: 20,
        lineWidthMinPixels: 2,
        getLineColor: [255, 0, 0], // 赤色の線
        getLineWidth: 2,
      }),
    );

    layerArr.push(
      new GeoJsonLayer<StopGeoJsonProp>({
        id: "station",
        data: stops,
        getText: (f: Feature<Point, StopGeoJsonProp>) => f.properties.stop_name,
        textCharacterSet: "auto",
        getPointRadius: 4,
        filled: true,
        getFillColor: [0xff, 0xff, 0xff],
        getTextColor: [0xff, 0xff, 0xff],
      }),
    );

    return layerArr;
  }, [stops, routes]);

  const loadStops = async () => {
    const resp = await fetch("/data/stops.json");
    const json = await resp.json();
    setStops(json);
  };

  const loadRoutes = async () => {
    const resp = await fetch("/data/shapes.json");
    const json = await resp.json();
    setRoutes(json);
  };

  useEffect(() => {
    Promise.all([loadStops(), loadRoutes()]).catch((e) =>
      console.error("cannot load data:", e),
    );
  }, []);

  return (
    <main className="absolute h-full w-full top-0 left-0">
      <Map
        initialViewState={INITIAL_VIEW_STATE}
        //mapStyle="https://tile.openstreetmap.jp/styles/osm-bright-ja/style.json"
        mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
        reuseMaps
        id="map"
      >
        <DeckGLOverlay controller layers={layers} />
      </Map>
    </main>
  );
}
