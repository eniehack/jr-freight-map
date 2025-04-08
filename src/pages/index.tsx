import { Geist, Geist_Mono } from "next/font/google";
import { MapViewState, DeckProps, LayersList } from '@deck.gl/core';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { Map, useControl } from 'react-map-gl/maplibre';
import { GeoJsonLayer } from '@deck.gl/layers';
import type {Feature, Geometry, FeatureCollection, Point} from 'geojson';
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useState } from "react";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const INITIAL_VIEW_STATE: MapViewState = {
  longitude: 139.767197,
  latitude: 35.681143,
  zoom: 13,
}

const DeckGLOverlay = (props: DeckProps) => {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props))
  overlay.setProps(props);
  return null
}
type GeoJsonProp = {
  name: string
}

export default function Home() {
  const [stations, setStations] = useState<null | FeatureCollection<Point, GeoJsonProp>>(null);

  const charset = useMemo<string[]>(() => {
    if (stations === null) return [];
    const chars = stations.features
      .map((d) => Array.from(d.properties.name)) //ラベル文字列を収集
      .flat();

    return Array.from(new Set(chars));
  }, [stations])

  const layers = useMemo<LayersList>(() => {
    const layerArr = []
    if (stations === null) {
      return []
    }
    layerArr.push(new GeoJsonLayer<GeoJsonProp>({
      id: 'station',
      data: stations,
      pointType: 'circle+text',
      getText: (f: Feature<Geometry, GeoJsonProp>) => f.properties.name,
      textCharacterSet: charset,
    }))
    return layerArr;
  }, [stations])

  useEffect(() => {
    const load = async () => {
      const resp = await fetch('/stations.json')
      const json = await resp.json()
      setStations(json)
    }
    load();
  })

  return (
    <main className="absolute h-full w-full top-0 left-0">
      <Map
        initialViewState={INITIAL_VIEW_STATE}
        mapStyle="https://tile.openstreetmap.jp/styles/osm-bright-ja/style.json"
        reuseMaps
        id="map"
      >
        <DeckGLOverlay layers={layers} />
      </Map>
    </main>
  );
}
