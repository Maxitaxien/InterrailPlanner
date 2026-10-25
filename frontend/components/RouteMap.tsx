"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { GeoJSONSource, Map as MapInstance, Marker } from "maplibre-gl";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import RailBookingDetails from "./RailBookingDetails";
import EndpointTransferDetails from "./EndpointTransferDetails";
import CityIdeas from "./CityIdeas";
import { ConnectionPlan } from "../lib/connection-types";

export type MapDestination = { id: string; name: string; country_code?: string; category?: string; latitude: number; longitude: number; is_endpoint?: boolean; interest_tags?: string[]; suggested_nights?: number; airport?: string | null };
export type RailEdge = { connection_plan?: ConnectionPlan; id: string; origin_id: string; destination_id: string; estimated_minutes: number; transfers: number; service_type: string; night_train: boolean; estimate_quality: string; reservation_warning?: string; source?: string; mode?: string; source_url?: string; booking_url?: string; onward_url?: string; components?: { mode: string; origin?: string; destination?: string; description?: string; estimated_minutes: number }[] };
type RouteStop = { destination_id: string; name: string; latitude: number; longitude: number; nights?: number; is_required?: boolean; is_locked?: boolean };
export type MapLeg = { origin_id: string; destination_id: string; via: string[]; estimated_minutes: number; mode?: string };
type Props = { destinations: MapDestination[]; network?: RailEdge[]; stops?: RouteStop[]; legs?: MapLeg[]; selectedIds?: string[]; onDestinationClick?: (destination: MapDestination) => void; planning?: boolean; busy?: boolean; focusCity?: { id: string }; travelClass?: 1 | 2; tripId?: string; token?: string; itineraryId?: string };
const EMPTY_STOPS: RouteStop[] = [];
const EMPTY_EDGES: RailEdge[] = [];
const EMPTY_LEGS: MapLeg[] = [];
const EMPTY_IDS: string[] = [];
const countryNames = new Intl.DisplayNames(["en"], { type: "region" });
const duration = (minutes: number) => `${Math.floor(minutes / 60)}h${minutes % 60 ? ` ${minutes % 60}m` : ""}`;
const keyFor = (a: string, b: string) => [a, b].sort().join(":");

export default function RouteMap({ destinations, network = EMPTY_EDGES, stops = EMPTY_STOPS, legs = EMPTY_LEGS, selectedIds = EMPTY_IDS, onDestinationClick, planning = false, busy = false, focusCity, travelClass = 2, tripId, token, itineraryId }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapInstance | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [ready, setReady] = useState(false);
  const [tileError, setTileError] = useState(false);
  const [cityId, setCityId] = useState<string | null>(null);
  const [edgeId, setEdgeId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [showNetwork, setShowNetwork] = useState(true);
  const markers = useRef<Marker[]>([]);
  const initialFit = useRef(false);
  const cities = useMemo(() => new Map(destinations.map(city => [city.id, city])), [destinations]);
  const city = cityId ? cities.get(cityId) : undefined;
  const cityDetails = useQuery({ queryKey: ["city-details", cityId], queryFn: () => api<{ attractions: { id: string; name: string; description: string }[] }>(`destinations/${encodeURIComponent(cityId!)}`), enabled: !!cityId, staleTime: 86400000 });
  const stop = stops.find(item => item.destination_id === cityId);
  const isSelected = !!cityId && selectedIds.includes(cityId);
  const protectedStop = cityId === "oslo" || !planning && !!stop && (stop.is_locked || stop.is_required || stops.at(-1)?.destination_id === cityId);
  const edges = useMemo(() => {
    const unique = new Map<string, RailEdge>();
    for (const edge of network) {
      const key = keyFor(edge.origin_id, edge.destination_id);
      if (!unique.has(key) || unique.get(key)!.estimated_minutes > edge.estimated_minutes) unique.set(key, edge);
    }
    return [...unique.values()];
  }, [network]);
  const activeEdge = edges.find(edge => edge.id === edgeId);
  const connections = cityId ? edges.filter(edge => edge.origin_id === cityId || edge.destination_id === cityId) : [];
  const connectedCities = useMemo(() => {
    const reachable = new Set(["oslo"]);
    const queue = ["oslo"];
    for (let index = 0; index < queue.length; index++) {
      for (const edge of network.filter(item => item.origin_id === queue[index])) {
        if (!reachable.has(edge.destination_id)) { reachable.add(edge.destination_id); queue.push(edge.destination_id); }
      }
    }
    return reachable;
  }, [network]);
  const disconnected = !!cityId && network.length > 0 && !connectedCities.has(cityId);
  const fitMap = (routeOnly = false) => {
    const points = routeOnly && stops.length ? stops : destinations;
    if (!map.current || !points.length) return;
    const longitudes = points.map(point => point.longitude);
    const latitudes = points.map(point => point.latitude);
    map.current.fitBounds([[Math.min(...longitudes), Math.min(...latitudes)], [Math.max(...longitudes), Math.max(...latitudes)]], { padding: { top: 65, bottom: 70, left: 60, right: 100 }, duration: 0, maxZoom: 7 });
  };

  useEffect(() => {
    if (!container.current) return;
    let cancelled = false;
    let instance: MapInstance | undefined;
    let observer: ResizeObserver | undefined;
    import("maplibre-gl").then(lib => {
      if (cancelled || !container.current) return;
      try {
        lib.setWorkerUrl(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());
        instance = new lib.Map({ container: container.current, center: [12, 50], zoom: 4, maxBounds: [[-25, 33], [45, 72]], renderWorldCopies: false, doubleClickZoom: false, style: {
          version: 8,
          sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>' } },
          layers: [
            { id: "background", type: "background", paint: { "background-color": "#e7ecdf" } },
            { id: "osm", type: "raster", source: "osm", paint: { "raster-saturation": -0.7, "raster-opacity": 0.75 } }
          ]
        } });
        map.current = instance;
        instance.addControl(new lib.NavigationControl({ showCompass: false }), "top-right");
        instance.addControl(new lib.FullscreenControl({ container: container.current.parentElement! }), "top-right");
        instance.on("load", () => {
          if (cancelled || !instance) return;
          for (const id of ["rail-network", "route"]) instance.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
          instance.addLayer({ id: "rail-network", type: "line", source: "rail-network", paint: { "line-color": ["case", ["==", ["get", "mode"], "ferry_transfer"], "#327ab5", "#567c79"], "line-width": 2, "line-opacity": 0.55, "line-dasharray": [3, 2] } });
          instance.addLayer({ id: "rail-hit", type: "line", source: "rail-network", paint: { "line-width": 16, "line-opacity": 0 } });
          instance.addLayer({ id: "active-rail", type: "line", source: "rail-network", filter: ["==", ["get", "id"], ""], paint: { "line-color": "#c1883e", "line-width": 5 } });
          instance.addLayer({ id: "route-halo", type: "line", source: "route", paint: { "line-color": "#fffdf6", "line-width": 8 } });
          instance.addLayer({ id: "route", type: "line", source: "route", filter: ["!=", ["get", "mode"], "ferry_transfer"], paint: { "line-color": "#28543e", "line-width": 4 } });
          instance.addLayer({ id: "route-transfer", type: "line", source: "route", filter: ["==", ["get", "mode"], "ferry_transfer"], paint: { "line-color": "#327ab5", "line-width": 4, "line-dasharray": [2, 2] } });
          instance.on("click", "rail-hit", event => {
            const id = event.features?.[0]?.properties?.id;
            if (id) { setEdgeId(String(id)); setCityId(null); }
          });
          instance.on("mouseenter", "rail-hit", () => { if (instance) instance.getCanvas().style.cursor = "pointer"; });
          instance.on("mouseleave", "rail-hit", () => { if (instance) instance.getCanvas().style.cursor = ""; });
          setReady(true);
        });
        instance.on("error", event => { if ("sourceId" in event && event.sourceId === "osm") setTileError(true); });
        if (typeof ResizeObserver !== "undefined") {
          observer = new ResizeObserver(() => instance?.resize());
          observer.observe(container.current);
        }
      } catch { setUnavailable(true); }
    }).catch(() => { if (!cancelled) setUnavailable(true); });
    return () => { cancelled = true; observer?.disconnect(); instance?.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    if (!focusCity) return;
    setCityId(focusCity.id); setEdgeId(null);
  }, [focusCity, cities]);

  useEffect(() => {
    if (!ready || !map.current) return;
    let cancelled = false;
    import("maplibre-gl").then(lib => {
      if (cancelled || !map.current) return;
      markers.current.forEach(marker => marker.remove());
      markers.current = [];
      destinations.forEach(destination => {
        const index = stops.findIndex(item => item.destination_id === destination.id);
        const selected = (!planning && index >= 0) || selectedIds.includes(destination.id) || destination.id === "oslo";
        const button = document.createElement("button");
        button.type = "button";
        button.className = `map-marker ${selected ? "is-selected" : ""} ${destination.id === cityId ? "is-focused" : ""}`;
        button.setAttribute("aria-label", `Explore ${destination.name}`);
        button.setAttribute("aria-pressed", String(destination.id === cityId));
        const dot = document.createElement("span");
        dot.textContent = index >= 0 ? String(index + 1) : destination.id === "oslo" ? "↗" : "+";
        const label = document.createElement("b");
        label.textContent = destination.name;
        button.append(dot, label);
        button.addEventListener("click", event => { event.stopPropagation(); setCityId(destination.id); setEdgeId(null); });
        markers.current.push(new lib.Marker({ element: button, anchor: "left", offset: [-12, 0] }).setLngLat([destination.longitude, destination.latitude]).addTo(map.current!));
      });
      const arrangeLabels = () => {
        if (!map.current) return;
        const occupied: { x: number; y: number; width: number }[] = [];
        const ranked = markers.current.map((marker, index) => ({ marker, destination: destinations[index] })).sort((a, b) => Number(b.marker.getElement().classList.contains("is-selected")) - Number(a.marker.getElement().classList.contains("is-selected")));
        ranked.forEach(({ marker, destination }) => {
          const point = map.current!.project([destination.longitude, destination.latitude]);
          const rect = { x: point.x, y: point.y, width: 30 + destination.name.length * 6 };
          const selected = marker.getElement().classList.contains("is-selected") || destination.id === cityId;
          const overlap = occupied.some(other => Math.abs(other.y - rect.y) < 25 && rect.x < other.x + other.width && other.x < rect.x + rect.width);
          marker.getElement().classList.toggle("map-label-muted", overlap && !selected);
          if (!overlap || selected) occupied.push(rect);
        });
      };
      map.current.on("moveend", arrangeLabels);
      cleanupLabels = () => map.current?.off("moveend", arrangeLabels);
      if (!initialFit.current && destinations.length) { fitMap(); initialFit.current = true; }
      arrangeLabels();
    });
    let cleanupLabels: (() => void) | undefined;
    return () => { cancelled = true; cleanupLabels?.(); };
    // Map creation is separate so edits and opening city details preserve pan/zoom.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, destinations, stops, selectedIds, cityId, planning]);

  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;
    const feature = (ids: string[], properties: Record<string, string | number>) => {
      const points = ids.map(id => cities.get(id)).filter((point): point is MapDestination => !!point);
      return { type: "Feature" as const, properties, geometry: { type: "LineString" as const, coordinates: points.map(point => [point.longitude, point.latitude]) } };
    };
    const networkFeatures = edges.filter(edge => cities.has(edge.origin_id) && cities.has(edge.destination_id)).map(edge => feature([edge.origin_id, edge.destination_id], { id: edge.id, mode: edge.mode || "rail" }));
    const routeFeatures = legs.length ? legs.map(leg => feature(leg.via, { minutes: leg.estimated_minutes, mode: leg.mode || "rail" })) : stops.length > 1 ? [feature(stops.map(item => item.destination_id), { mode: "rail" })] : [];
    (instance.getSource("rail-network") as GeoJSONSource).setData({ type: "FeatureCollection", features: networkFeatures });
    (instance.getSource("route") as GeoJSONSource).setData({ type: "FeatureCollection", features: routeFeatures });
    instance.setLayoutProperty("rail-network", "visibility", showNetwork ? "visible" : "none");
    instance.setLayoutProperty("rail-hit", "visibility", showNetwork ? "visible" : "none");
    instance.setLayoutProperty("active-rail", "visibility", showNetwork ? "visible" : "none");
    instance.setFilter("active-rail", ["==", ["get", "id"], edgeId || ""]);
  }, [ready, cities, edges, legs, stops, showNetwork, edgeId]);

  const chooseCity = (id: string) => {
    setCityId(id); setEdgeId(null); setSearch("");
  };
  const actionLabel = cityId === "oslo" ? "Oslo is your starting point" : planning ? city?.category === "island" ? "Make island final destination" : city?.category === "coastal" ? "Make coastal final destination" : isSelected ? "Remove must-see stop" : "Add must-see stop" : disconnected ? "No connected rail corridor" : stop ? protectedStop ? "Required, locked or final stop" : "Remove from route" : city?.is_endpoint ? "Make final destination" : "Add to route";

  return <section className="map-explorer" aria-label={planning ? "Choose trip stops" : "Explore rail route"}>
    <div className="map-toolbar"><div><span className="eyebrow">EUROPE BY RAIL</span><h3>{planning ? "Where will you stop?" : "Your journey, on the map."}</h3></div><div className="map-tools"><label className="map-search">Find a city<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search cities…" /></label><button type="button" onClick={() => fitMap(stops.length > 0)}>Fit {stops.length ? "route" : "Europe"}</button><button type="button" aria-pressed={showNetwork} onClick={() => setShowNetwork(value => !value)}>Rail connections</button></div></div>
    {search && <div className="city-search-results">{destinations.filter(item => item.name.toLowerCase().includes(search.toLowerCase())).slice(0, 12).map(item => <button type="button" key={item.id} onClick={() => chooseCity(item.id)}>{item.name} <small>{item.country_code}</small></button>)}</div>}
    <div className="map-shell">
      <div ref={container} className="map" aria-label={planning ? "Map for choosing trip stops" : "Interactive route map"} />
      {unavailable && <div className="map-fallback"><strong>Interactive maps need WebGL.</strong><p>Explore cities and edit stops using the city picker below.</p></div>}
      {(city || activeEdge) && <div className="map-detail" aria-label={city ? `${city.name} city details` : "Rail connection details"}>
        <button type="button" className="map-detail-close" aria-label="Close map details" onClick={() => { setCityId(null); setEdgeId(null); }}>×</button>
        {city && <>
          <p className="eyebrow">{city.country_code ? countryNames.of(city.country_code) : "Explore"}{stop ? " · ON YOUR ROUTE" : ""}</p>
          <h3>{city.name}</h3><p>{stop ? stop.nights === 0 ? city.id === "oslo" ? "Departure city" : "Day visit · no overnight stay" : `${stop.nights ?? 0} nights in your itinerary` : `Allow ${city.suggested_nights ?? 2} nights to explore`}</p>
          <div className="city-tags">{city.interest_tags?.map(tag => <span key={tag}>{tag}</span>)}</div>
          <p className="city-facts">{disconnected ? "A supported international connection to this city has not been added to the planner." : city.category === "island" ? "Island final stay. Check the listed ferry and ground connections, local beach transport and return airport access separately." : city.category === "coastal" && city.country_code === "GR" ? "Final stay via an Italy–Greece ferry and the listed onward transfers. Follow the named arrival port; road-transfer allowances do not confirm a scheduled bus." : city.id === "athens" ? "Available as an endpoint via Bari–Patras ferry and onward ground travel. Book and verify these separately; no continuous international train is implied." : city.is_endpoint ? `Available as a final stay${city.airport ? ` · nearby airport ${city.airport}` : ""}.` : "Explore the city, then continue by rail."}</p>
          {cityDetails.data?.attractions.map(attraction => <div className="city-highlight" key={attraction.id}><h4>{attraction.name}</h4><p>{attraction.description}</p></div>)}
          <a href={`https://en.wikivoyage.org/wiki/${encodeURIComponent(city.name.split(" · ")[0])}`} target="_blank" rel="noopener noreferrer">City guide ↗</a>
          <CityIdeas key={city.id} destinationId={city.id} name={city.name} tripId={tripId} token={token} itineraryId={itineraryId} />
          <button type="button" className="city-action" disabled={busy || protectedStop || (disconnected && !planning)} onClick={() => onDestinationClick?.(city)}>{busy ? "Saving…" : actionLabel}</button>
          <h4>Connections · estimates</h4><ul className="city-connections">{connections.map(edge => {
            const other = edge.origin_id === city.id ? edge.destination_id : edge.origin_id;
            return <li key={edge.id}><button type="button" onClick={() => chooseCity(other)}>{cities.get(other)?.name || other}</button><span>{duration(edge.estimated_minutes)}{edge.mode === "ferry_transfer" ? " · ferry / ground transfer" : " · rail"}</span></li>;
          })}</ul>{!connections.length && <p>No connections loaded for this city.</p>}
        </>}
        {activeEdge && <><p className="eyebrow">{activeEdge.mode === "ferry_transfer" ? "ENDPOINT FERRY + TRANSFER" : "RAIL CORRIDOR"}</p><h3>{cities.get(activeEdge.origin_id)?.name} → {cities.get(activeEdge.destination_id)?.name}</h3><p>{duration(activeEdge.estimated_minutes)} estimated · {activeEdge.service_type}</p><p>{activeEdge.mode === "ferry_transfer" ? "Illustrative ferry / ground transfer allowance" : activeEdge.night_train ? "Overnight service" : "Daytime corridor"} · {activeEdge.transfers ? `around ${activeEdge.transfers} change(s)` : "no changes modeled"}</p><small>{activeEdge.reservation_warning || "Check departures and reservations before booking."}</small><div className="edge-cities">{[activeEdge.origin_id, activeEdge.destination_id].map(id => <button type="button" key={id} onClick={() => chooseCity(id)}>Explore {cities.get(id)?.name}</button>)}</div>{activeEdge.mode === "ferry_transfer" ? <EndpointTransferDetails transfers={[activeEdge]} /> : <RailBookingDetails key={activeEdge.id} originId={activeEdge.origin_id} destinationId={activeEdge.destination_id} travelClass={travelClass} />}</>}
      </div>}
      <div className="map-legend"><span><i className="legend-line" /> your rail route</span><span><i className="legend-line network" /> rail corridor</span><span><i className="legend-line ferry" /> ferry + transfer</span><span>Click cities or connections to explore</span></div>
    </div>
    <div className="map-footer"><span>{destinations.length} cities · {edges.length} planning corridors{tileError ? " · Some background tiles could not load" : ""}</span><a href="https://www.interrail.com/en/plan-your-trip/interrail-railway-map" target="_blank" rel="noopener noreferrer">Full Interrail network ↗</a><span>Schematic lines · travel times are estimates</span></div>
    <details className="city-picker"><summary>Browse all cities · keyboard & offline access</summary><div className="chips">{destinations.map(item => <button type="button" key={item.id} onClick={() => chooseCity(item.id)}>{item.name}</button>)}</div></details>
  </section>;
}
