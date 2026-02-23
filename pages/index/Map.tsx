import { MapViewState, DeckProps, PickingInfo, LayerProps, Accessor, Color, MapView } from "@deck.gl/core";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { Map, useControl, AttributionControl } from "react-map-gl/maplibre";
import { GeoJsonLayer } from "@deck.gl/layers";
import { TripsLayer } from "@deck.gl/geo-layers";
import { DeckGL } from "@deck.gl/react";
import type { Feature, Geometry, Point } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";

dayjs.extend(utc);
dayjs.extend(timezone);

const INITIAL_VIEW_STATE: MapViewState = {
  longitude: 139.80034,
  latitude: 35.73272,
  zoom: 5,
};

const DeckGLOverlay = (props: DeckProps) => {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props));
  overlay.setProps(props);
  return null;
};

interface StopGeoJsonProp {
  id: string;
  name: string;
}

interface StopTimesJson {
  id: string;
  ts: number[];
  c: [number, number][];
  dpt: string;
  dst: string;
}

export default function MapComponent() {
  const [timestamp, setTimestamp] = useState<number>(0);
  const [timeSpeed, setTimeSpeed] = useState<number>(1);
  const [zoomLevel, setZoomLevel] = useState<number>(INITIAL_VIEW_STATE.zoom);
  const [isPanelOpened, setPanelOpened] = useState(false);
  const [selectedTrain, setSelectedTrain] = useState<null | StopTimesJson>(null);

  const getTooltip = useCallback(({ object }: PickingInfo<StopTimesJson>) => {
    return object ? `${object.dpt} - ${object.dst}` : null;
  }, []);

  const humanizedTime = useMemo(() => {
    return dayjs.unix(timestamp).subtract(9, "hours").format("HH:mm:ss");
  }, [timestamp]);

  const getStationName = useCallback((f: Feature<Point, StopGeoJsonProp>) => {
    return f.properties.name;
  }, []);

  const tripLayerOnClicked: LayerProps["onClick"] = useCallback((info: PickingInfo<StopTimesJson>, event: any) => {
    console.log("clicked", info, event);
    if (typeof info.object !== "undefined") {
      setPanelOpened(true);
      setSelectedTrain(info.object);
    }
  }, []);

  const TripColors: Record<string, Color> = useMemo(() => {
    return {
      selected: [86, 89, 58],
      normal: [0x8a, 0x58, 0x87],
    };
  }, []);

  const setTripsColor: Accessor<StopTimesJson, Color | Color[]> = useCallback(
    (json: StopTimesJson): Color | Color[] => {
      if (selectedTrain && json.id === selectedTrain.id) {
        return TripColors.selected;
      }
      return TripColors.normal;
    },
    [TripColors, selectedTrain],
  );

  const stopsFillColor: Record<string, Color> = useMemo(() => {
    return {
      selected: [0, 0xff, 0],
      normal: [0xff, 0xff, 0xff],
    };
  }, []);

  const setStopsJsonFillColor: Accessor<Feature<Geometry, StopGeoJsonProp>, Color> = useCallback(
    (stops: Feature<Geometry, StopGeoJsonProp>) => {
      if (
        selectedTrain &&
        (stops.properties.name === selectedTrain.dpt || stops.properties.name === selectedTrain.dst)
      ) {
        return stopsFillColor.selected;
      }
      return stopsFillColor.normal;
    },
    [selectedTrain, stopsFillColor],
  );

  const setCurrentTime = () => {
    const now = dayjs().unix();
    const startOfToday = dayjs().startOf("date").unix();
    setTimestamp(() => now - startOfToday);
  };

  const convertTimestampToTime = (timestamp: number): string => {
    return dayjs().startOf("date").add(timestamp, "second").format("HH:mm");
  };

  const lastUpdateRef = useRef(Date.now());

  useEffect(() => {
    if (timeSpeed === 0) return;

    const animate = () => {
      const now = Date.now();
      const deltaMs = now - lastUpdateRef.current;
      lastUpdateRef.current = now;
      const deltaSeconds = (deltaMs / 1000) * timeSpeed;
      setTimestamp((prev) => {
        const next = prev + deltaSeconds;
        return 86400 <= next ? 0 : next;
      });
      animationFrameId = requestAnimationFrame(animate);
    };
    let animationFrameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrameId);
  }, [timeSpeed]);

  return (
    <>
      <div className="absolute h-full w-full top-0 left-0">
        <DeckGL initialViewState={INITIAL_VIEW_STATE} controller getTooltip={getTooltip}>
          <GeoJsonLayer
            id="station-layer"
            data={`${import.meta.env.BASE_URL}stops.json`}
            pointType="circle+text"
            getText={getStationName}
            textCharacterSet="auto"
            textFontFamily="Noto Sans JP"
            getTextSize={16}
            getTextPixelOffset={[0, 30]}
            getTextAlignmentBaseline="bottom"
            getPointRadius={4}
            pointRadiusMaxPixels={5}
            pointRadiusMinPixels={5}
            filled={true}
            getFillColor={setStopsJsonFillColor}
            getTextColor={[0xff, 0xff, 0xff]}
            _subLayerProps={{
              "points-text": {
                visible: 9 < zoomLevel,
              },
            }}
            updateTriggers={{
              getFillColor: { selectedTrain },
            }}
          />
          <TripsLayer
            id="trips"
            data={`${import.meta.env.BASE_URL}stop_times.json`}
            getPath={(d: StopTimesJson) => d.c}
            getTimestamps={(d: StopTimesJson) => d.ts}
            opacity={0.6}
            widthMinPixels={6}
            getColor={setTripsColor}
            currentTime={timestamp}
            //trailLength={300}
            capRounded={true}
            jointRounded={true}
            pickable={true}
            onClick={tripLayerOnClicked}
            updateTriggers={{
              getColor: { selectedTrain },
            }}
          />
          <MapView id="map" controller>
            <Map
              mapStyle={`${import.meta.env.BASE_URL}style.json`}
              //mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
              reuseMaps
              attributionControl={false}
              id="map"
            >
              <AttributionControl
                compact={true}
                customAttribution="© <a href='https://ckan.odpt.org/dataset/jrfreight_container'>JR貨物・国土交通省・公共交通オープンデータ協議会</a>"
              />
            </Map>
          </MapView>
        </DeckGL>
      </div>
      {isPanelOpened && selectedTrain !== null && (
        <div
          className="absolute z-10 top-0 left-0 h-full w-80 bg-white shadow-lg
        transform transition-transform duration-300 container"
        >
          <div className="flex flex-row flex-[auto_1] gap-2 m-3">
            <h1>列車詳細</h1>
            <button onClick={() => setSelectedTrain(null)}>✕</button>
          </div>
          <span>
            {convertTimestampToTime(selectedTrain.ts[0])}: {selectedTrain.dpt}発
          </span>
          <span>
            {convertTimestampToTime(selectedTrain.ts[selectedTrain.ts.length - 1])}: {selectedTrain.dst}着
          </span>
        </div>
      )}
      <div className="absolute z-10 bottom-2 left-1 bg-white p-4 rounded-md">
        <p>
          時刻: <span>{humanizedTime}</span>
        </p>
        <select id="timespeed" value={timeSpeed} onChange={(event) => setTimeSpeed(Number(event.target.value))}>
          {[
            { value: 1, text: "1倍" },
            { value: 60, text: "60倍" },
            { value: 300, text: "300倍" },
            { value: 600, text: "600倍" },
          ].map((elem) => (
            <option key={elem.value} value={elem.value}>
              {elem.text}
            </option>
          ))}
        </select>
        <label htmlFor="timespeed">倍速</label>
        <button
          type="button"
          className={`rounded-md p-2 text-gray-200 ${timeSpeed === 0 ? "bg-green-500" : "bg-red-500"}`}
          onClick={() => setTimeSpeed(timeSpeed === 0 ? 1 : 0)}
        >
          {timeSpeed === 0 ? "再生" : "停止"}
        </button>
        <div className="flex gap-1">
          <button className="rounded-md bg-blue-500 px-1" onClick={() => setTimestamp(timestamp + 60 * 60)}>
            +1H
          </button>
          <button className="bg-blue-500 rounded-md p-1" onClick={() => setCurrentTime()}>
            現在時刻
          </button>
        </div>
      </div>
    </>
  );
}
