import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  GeoJSON,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";

const API_URL = "http://localhost:8001";

const INDIA_CENTER = [22.5, 79.0];

const FALLBACK_LOCATIONS = [
  {
    id: "depot-a",
    code: "DEPOT-A",
    name: "Demo Depot A",
    location_type: "DEPOT",
    latitude: 19.076,
    longitude: 72.8777,
  },
  {
    id: "forward-b",
    code: "FORWARD-B",
    name: "Synthetic Forward Point B",
    location_type: "FORWARD_BASE",
    latitude: 19.2183,
    longitude: 72.9781,
  },
];

/* =========================================================
   HELPERS
   ========================================================= */

function toNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function extractCoordinates(object) {
  if (!object) {
    return null;
  }

  let latitude =
    object.latitude ??
    object.lat ??
    object.current_latitude ??
    object.current_lat;

  let longitude =
    object.longitude ??
    object.lon ??
    object.lng ??
    object.current_longitude ??
    object.current_lon ??
    object.current_lng;

  if (
    latitude === undefined ||
    latitude === null ||
    longitude === undefined ||
    longitude === null
  ) {
    const coordinates =
      object.coordinates ||
      object.geometry?.coordinates;

    if (
      Array.isArray(coordinates) &&
      coordinates.length >= 2 &&
      typeof coordinates[0] !== "object"
    ) {
      longitude = coordinates[0];
      latitude = coordinates[1];
    }
  }

  latitude = toNumber(latitude);
  longitude = toNumber(longitude);

  if (
    latitude === null ||
    longitude === null ||
    latitude < -90 ||
    latitude > 90 ||
    longitude < -180 ||
    longitude > 180
  ) {
    return null;
  }

  return [latitude, longitude];
}

function createIcon(type) {
  let color = "#596b3a";

  if (type === "FORWARD_BASE") {
    color = "#c58b3c";
  }

  if (type === "VEHICLE") {
    color = "#167c80";
  }

  return L.divIcon({
    className: "custom-marker-wrapper",
    html: `
      <div class="custom-marker" style="--marker-color:${color}">
        <span></span>
      </div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -12],
  });
}

async function fetchJson(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

/* =========================================================
   GEOJSON SIMPLIFICATION
   ========================================================= */

/*
 * The downloaded India boundary contains a very large number
 * of coordinate points.
 *
 * We simplify it before giving it to Leaflet.
 * This keeps the overall boundary shape while dramatically
 * reducing browser rendering cost.
 */

function perpendicularDistance(point, start, end) {
  const x = point[0];
  const y = point[1];

  const x1 = start[0];
  const y1 = start[1];

  const x2 = end[0];
  const y2 = end[1];

  const dx = x2 - x1;
  const dy = y2 - y1;

  if (dx === 0 && dy === 0) {
    return Math.sqrt(
      Math.pow(x - x1, 2) +
        Math.pow(y - y1, 2)
    );
  }

  const t =
    ((x - x1) * dx +
      (y - y1) * dy) /
    (dx * dx + dy * dy);

  const clampedT = Math.max(
    0,
    Math.min(1, t)
  );

  const closestX =
    x1 + clampedT * dx;

  const closestY =
    y1 + clampedT * dy;

  return Math.sqrt(
    Math.pow(x - closestX, 2) +
      Math.pow(y - closestY, 2)
  );
}

function simplifyLine(points, tolerance = 0.02) {
  if (!Array.isArray(points) || points.length <= 2) {
    return points;
  }

  let maxDistance = 0;
  let index = 0;

  const firstPoint = points[0];
  const lastPoint =
    points[points.length - 1];

  for (
    let i = 1;
    i < points.length - 1;
    i++
  ) {
    const distance =
      perpendicularDistance(
        points[i],
        firstPoint,
        lastPoint
      );

    if (distance > maxDistance) {
      index = i;
      maxDistance = distance;
    }
  }

  if (maxDistance > tolerance) {
    const left = simplifyLine(
      points.slice(0, index + 1),
      tolerance
    );

    const right = simplifyLine(
      points.slice(index),
      tolerance
    );

    return [
      ...left.slice(0, -1),
      ...right,
    ];
  }

  return [
    firstPoint,
    lastPoint,
  ];
}

function simplifyCoordinates(
  coordinates,
  tolerance = 0.02
) {
  if (!Array.isArray(coordinates)) {
    return coordinates;
  }

  if (
    coordinates.length === 0
  ) {
    return coordinates;
  }

  /*
   * Coordinate pair:
   * [longitude, latitude]
   */
  if (
    typeof coordinates[0] === "number"
  ) {
    return coordinates;
  }

  /*
   * LineString
   */
  if (
    Array.isArray(coordinates[0]) &&
    typeof coordinates[0][0] === "number"
  ) {
    return simplifyLine(
      coordinates,
      tolerance
    );
  }

  return coordinates.map(
    (child) =>
      simplifyCoordinates(
        child,
        tolerance
      )
  );
}

function simplifyGeoJSON(
  geojson,
  tolerance = 0.02
) {
  if (!geojson) {
    return null;
  }

  if (geojson.type === "FeatureCollection") {
    return {
      ...geojson,
      features: geojson.features.map(
        (feature) =>
          simplifyGeoJSON(
            feature,
            tolerance
          )
      ),
    };
  }

  if (geojson.type === "Feature") {
    return {
      ...geojson,
      geometry: geojson.geometry
        ? {
            ...geojson.geometry,
            coordinates:
              simplifyCoordinates(
                geojson.geometry.coordinates,
                tolerance
              ),
          }
        : null,
    };
  }

  if (geojson.coordinates) {
    return {
      ...geojson,
      coordinates:
        simplifyCoordinates(
          geojson.coordinates,
          tolerance
        ),
    };
  }

  return geojson;
}

/* =========================================================
   MAP CONTROLLER
   ========================================================= */

function MapController({ locations }) {
  const map = useMap();

  useEffect(() => {
    const validCoordinates = locations
      .map(extractCoordinates)
      .filter(Boolean);

    if (
      validCoordinates.length >= 2
    ) {
      map.fitBounds(
        validCoordinates,
        {
          padding: [70, 70],
          maxZoom: 7,
        }
      );
    }
  }, [map, locations]);

  return null;
}

/* =========================================================
   INDIA BOUNDARY
   ========================================================= */

function IndiaBoundary() {
  const [boundary, setBoundary] =
    useState(null);

  useEffect(() => {
    let cancelled = false;

    async function loadBoundary() {
      try {
        /*
         * Wait until the actual OSM map has rendered.
         */
        await new Promise(
          (resolve) =>
            setTimeout(resolve, 700)
        );

        const response = await fetch(
          "/india-composite.geojson"
        );

        if (!response.ok) {
          throw new Error(
            `India boundary request failed: ${response.status}`
          );
        }

        const original =
          await response.json();

        if (cancelled) {
          return;
        }

        /*
         * Light simplification.
         *
         * We are NOT replacing the source.
         * We are reducing unnecessary points
         * only for browser rendering.
         */
        const simplified =
          simplifyGeoJSON(
            original,
            0.015
          );

        if (!cancelled) {
          setBoundary(simplified);
        }
      } catch (error) {
        console.error(
          "India boundary error:",
          error
        );
      }
    }

    loadBoundary();

    return () => {
      cancelled = true;
    };
  }, []);

  if (!boundary) {
    return null;
  }

  return (
    <GeoJSON
      data={boundary}
      style={{
        color: "#4f6038",
        weight: 2,
        opacity: 0.95,
        fillColor: "#72824e",
        fillOpacity: 0.035,
      }}
    />
  );
}

/* =========================================================
   MAIN APP
   ========================================================= */

function App() {
  const [activeView, setActiveView] =
    useState("operations");

  const [theme, setTheme] =
    useState("light");

  const [commandOpen, setCommandOpen] =
    useState(false);

  const [gisData, setGisData] =
    useState(null);

  const [inventory, setInventory] =
    useState([]);

  const [vehicles, setVehicles] =
    useState([]);

  const [shipments, setShipments] =
    useState([]);

  const [selectedObject, setSelectedObject] =
    useState(null);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  useEffect(() => {
    loadOperationalData();
  }, []);

  useEffect(() => {
    function handleKeyboard(event) {
      if (
        (event.ctrlKey ||
          event.metaKey) &&
        event.key.toLowerCase() === "k"
      ) {
        event.preventDefault();
        setCommandOpen(true);
      }

      if (event.key === "Escape") {
        setCommandOpen(false);
      }
    }

    window.addEventListener(
      "keydown",
      handleKeyboard
    );

    return () => {
      window.removeEventListener(
        "keydown",
        handleKeyboard
      );
    };
  }, []);

  async function loadOperationalData() {
    setLoading(true);
    setError("");

    try {
      const [
        gisResponse,
        inventoryResponse,
        vehiclesResponse,
        shipmentsResponse,
      ] = await Promise.all([
        fetchJson(
          `${API_URL}/api/gis/operational-layer`
        ),
        fetchJson(
          `${API_URL}/api/logistics/inventory`
        ),
        fetchJson(
          `${API_URL}/api/logistics/vehicles`
        ),
        fetchJson(
          `${API_URL}/api/logistics/shipments`
        ),
      ]);

      setGisData(gisResponse);

      setInventory(
        inventoryResponse.inventory || []
      );

      setVehicles(
        vehiclesResponse.vehicles || []
      );

      setShipments(
        shipmentsResponse.shipments || []
      );
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const locations = useMemo(() => {
    const backendLocations =
      gisData?.locations || [];

    const validLocations =
      backendLocations.filter(
        (location) =>
          extractCoordinates(location)
      );

    return validLocations.length > 0
      ? validLocations
      : FALLBACK_LOCATIONS;
  }, [gisData]);

  const mapVehicles = useMemo(() => {
    return (
      gisData?.vehicles ||
      vehicles ||
      []
    ).filter((vehicle) =>
      extractCoordinates(vehicle)
    );
  }, [gisData, vehicles]);

  const depot = locations.find(
    (location) =>
      location.code === "DEPOT-A" ||
      location.location_type ===
        "DEPOT"
  );

  const forwardBase =
    locations.find(
      (location) =>
        location.code ===
          "FORWARD-B" ||
        location.location_type ===
          "FORWARD_BASE"
    );

  const depotCoordinates =
    extractCoordinates(depot);

  const forwardCoordinates =
    extractCoordinates(
      forwardBase
    );

  const routeCoordinates =
    depotCoordinates &&
    forwardCoordinates
      ? [
          depotCoordinates,
          forwardCoordinates,
        ]
      : [];

  const availableVehicles =
    vehicles.filter(
      (vehicle) =>
        vehicle.status ===
        "AVAILABLE"
    );

  const deliveredShipments =
    shipments.filter(
      (shipment) =>
        shipment.status ===
        "DELIVERED"
    );

  function selectView(view) {
    setActiveView(view);
    setSelectedObject(null);
    setCommandOpen(false);
  }

  return (
    <div
      className={`app-shell ${
        theme === "dark"
          ? "theme-dark"
          : ""
      }`}
    >
      <aside className="command-rail">
        <div className="brand-mark">
          TL
        </div>

        <nav className="rail-navigation">
          <button
            className={
              activeView ===
              "operations"
                ? "active"
                : ""
            }
            onClick={() =>
              selectView(
                "operations"
              )
            }
          >
            <span className="nav-icon">
              OPS
            </span>
            <small>
              Operations
            </small>
          </button>

          <button
            className={
              activeView ===
              "movement"
                ? "active"
                : ""
            }
            onClick={() =>
              selectView(
                "movement"
              )
            }
          >
            <span className="nav-icon">
              ↗
            </span>
            <small>
              Movement
            </small>
          </button>

          <button
            className={
              activeView ===
              "supply"
                ? "active"
                : ""
            }
            onClick={() =>
              selectView(
                "supply"
              )
            }
          >
            <span className="nav-icon">
              ▣
            </span>
            <small>
              Supply
            </small>
          </button>

          <button
            className={
              activeView ===
              "intelligence"
                ? "active"
                : ""
            }
            onClick={() =>
              selectView(
                "intelligence"
              )
            }
          >
            <span className="nav-icon">
              AI
            </span>
            <small>
              Intelligence
            </small>
          </button>

          <button
            className={
              activeView === "data"
                ? "active"
                : ""
            }
            onClick={() =>
              selectView("data")
            }
          >
            <span className="nav-icon">
              DB
            </span>
            <small>Data</small>
          </button>
        </nav>

        <div className="rail-bottom">
          <button
            onClick={() =>
              setTheme(
                theme === "light"
                  ? "dark"
                  : "light"
              )
            }
          >
            {theme === "light"
              ? "☾"
              : "☀"}
          </button>

          <button
            onClick={() =>
              setCommandOpen(true)
            }
          >
            ⌘
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="topbar-title">
            <span className="eyebrow">
              PREDICTIVE LOGISTICS
            </span>

            <h1>
              {activeView ===
                "operations" &&
                "Operational Picture"}

              {activeView ===
                "movement" &&
                "Movement Intelligence"}

              {activeView ===
                "supply" &&
                "Supply Network"}

              {activeView ===
                "intelligence" &&
                "Decision Intelligence"}

              {activeView === "data" &&
                "Data Observatory"}
            </h1>
          </div>

          <div className="topbar-actions">
            <div className="system-status">
              <span className="status-dot"></span>
              System Operational
            </div>

            <button
              className="command-button"
              onClick={() =>
                setCommandOpen(true)
              }
            >
              <span>⌘K</span>
              Command
            </button>

            <button
              className="refresh-button"
              onClick={
                loadOperationalData
              }
            >
              ↻
            </button>
          </div>
        </header>

        {error && (
          <div className="error-banner">
            <strong>
              Data connection issue:
            </strong>{" "}
            {error}
          </div>
        )}

        {activeView ===
          "operations" && (
          <OperationsView
            loading={loading}
            locations={locations}
            mapVehicles={
              mapVehicles
            }
            depot={depot}
            forwardBase={
              forwardBase
            }
            depotCoordinates={
              depotCoordinates
            }
            forwardCoordinates={
              forwardCoordinates
            }
            routeCoordinates={
              routeCoordinates
            }
            selectedObject={
              selectedObject
            }
            setSelectedObject={
              setSelectedObject
            }
            inventory={inventory}
            shipments={shipments}
            availableVehicles={
              availableVehicles
            }
            deliveredShipments={
              deliveredShipments
            }
          />
        )}

        {activeView ===
          "movement" && (
          <MovementView
            shipments={shipments}
            vehicles={vehicles}
          />
        )}

        {activeView === "supply" && (
          <SupplyView
            inventory={inventory}
            locations={locations}
          />
        )}

        {activeView ===
          "intelligence" && (
          <IntelligenceView />
        )}

        {activeView === "data" && (
          <DataView
            gisData={gisData}
            inventory={inventory}
            vehicles={vehicles}
            shipments={shipments}
          />
        )}
      </main>

      {commandOpen && (
        <CommandPalette
          close={() =>
            setCommandOpen(false)
          }
          selectView={selectView}
        />
      )}
    </div>
  );
}

/* =========================================================
   OPERATIONS
   ========================================================= */

function OperationsView({
  loading,
  locations,
  mapVehicles,
  depot,
  forwardBase,
  depotCoordinates,
  forwardCoordinates,
  routeCoordinates,
  selectedObject,
  setSelectedObject,
  inventory,
  shipments,
  availableVehicles,
  deliveredShipments,
}) {
  const mapObjects = [
    ...locations.map(
      (location) => ({
        ...location,
        objectType:
          location.location_type ||
          "LOCATION",
      })
    ),

    ...mapVehicles.map(
      (vehicle) => ({
        ...vehicle,
        objectType: "VEHICLE",
      })
    ),
  ];

  return (
    <div className="operations-workspace">
      <section className="attention-strip">
        <div className="attention-main">
          <span className="attention-label">
            LIVE OPERATIONAL FEED
          </span>

          <strong>
            {loading
              ? "Synchronizing logistics picture..."
              : "Network synchronized with logistics backend"}
          </strong>
        </div>

        <div className="attention-items">
          <span className="healthy">
            ● {locations.length} Locations
          </span>

          <span className="movement">
            ● {mapVehicles.length} Vehicles
          </span>

          <span className="neutral">
            ● {shipments.length} Shipments
          </span>
        </div>
      </section>

      <section className="kpi-strip">
        <KpiCard
          title="Inventory Positions"
          value={inventory.length}
          subtitle="Tracked"
        />

        <KpiCard
          title="Available Vehicles"
          value={
            availableVehicles.length
          }
          subtitle="Ready for movement"
        />

        <KpiCard
          title="Active Shipments"
          value={shipments.length}
          subtitle="Across network"
        />

        <KpiCard
          title="Delivered"
          value={
            deliveredShipments.length
          }
          subtitle="Completed movements"
        />
      </section>

      <section className="map-workspace">
        <div className="map-panel">
          <div className="map-header">
            <div>
              <span className="eyebrow">
                GIS OPERATIONAL LAYER
              </span>

              <h2>
                India Logistics Network
              </h2>
            </div>

            <div className="map-legend">
              <span>
                <i className="legend-dot depot"></i>
                Depot
              </span>

              <span>
                <i className="legend-dot forward"></i>
                Forward
              </span>

              <span>
                <i className="legend-dot vehicle"></i>
                Vehicle
              </span>
            </div>
          </div>

          <div className="real-map">
            <MapContainer
              center={INDIA_CENTER}
              zoom={5}
              minZoom={4}
              maxZoom={15}
              scrollWheelZoom={true}
              zoomControl={true}
              preferCanvas={true}
              style={{
                width: "100%",
                height: "100%",
              }}
            >
              <TileLayer
                attribution="&copy; OpenStreetMap contributors"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />

              <IndiaBoundary />

              <MapController
                locations={locations}
              />

              {mapObjects.map(
                (
                  object,
                  index
                ) => {
                  const coordinates =
                    extractCoordinates(
                      object
                    );

                  if (
                    !coordinates
                  ) {
                    return null;
                  }

                  const type =
                    object.objectType ===
                    "VEHICLE"
                      ? "VEHICLE"
                      : object.location_type;

                  return (
                    <Marker
                      key={`marker-${
                        object.id ||
                        object.code ||
                        index
                      }`}
                      position={
                        coordinates
                      }
                      icon={createIcon(
                        type
                      )}
                      eventHandlers={{
                        click: () =>
                          setSelectedObject(
                            object
                          ),
                      }}
                    >
                      <Popup>
                        <strong>
                          {object.vehicle_code ||
                            object.code ||
                            object.name ||
                            "Operational Object"}
                        </strong>

                        <br />

                        {object.objectType ===
                        "VEHICLE"
                          ? `${
                              object.vehicle_type ||
                              "Vehicle"
                            } · ${
                              object.status ||
                              "UNKNOWN"
                            }`
                          : object.location_type ||
                            "Location"}
                      </Popup>
                    </Marker>
                  );
                }
              )}

              {routeCoordinates.length ===
                2 && (
                <Polyline
                  positions={
                    routeCoordinates
                  }
                  pathOptions={{
                    color:
                      "#167c80",
                    weight: 4,
                    opacity: 0.85,
                    dashArray:
                      "10 8",
                  }}
                />
              )}
            </MapContainer>
          </div>
        </div>

        <ContextPanel
          selectedObject={
            selectedObject
          }
          depot={depot}
          forwardBase={
            forwardBase
          }
          depotCoordinates={
            depotCoordinates
          }
          forwardCoordinates={
            forwardCoordinates
          }
          inventory={inventory}
          shipments={shipments}
        />
      </section>
    </div>
  );
}

function KpiCard({
  title,
  value,
  subtitle,
}) {
  return (
    <div className="kpi-card">
      <span>{title}</span>

      <strong>{value}</strong>

      <small>{subtitle}</small>
    </div>
  );
}

/* =========================================================
   CONTEXT PANEL
   ========================================================= */

function ContextPanel({
  selectedObject,
  depot,
  forwardBase,
  depotCoordinates,
  forwardCoordinates,
  inventory,
  shipments,
}) {
  const object =
    selectedObject || depot;

  if (!object) {
    return (
      <aside className="context-panel">
        <span className="eyebrow">
          CONTEXT
        </span>

        <h2>
          No object selected
        </h2>

        <p>
          Select a location or
          vehicle on the map.
        </p>
      </aside>
    );
  }

  const coordinates =
    extractCoordinates(object);

  return (
    <aside className="context-panel">
      <div className="context-header">
        <div>
          <span className="eyebrow">
            {object.objectType ||
              object.location_type ||
              "LOCATION"}
          </span>

          <h2>
            {object.vehicle_code ||
              object.code ||
              object.name ||
              "Operational Object"}
          </h2>
        </div>

        <span className="context-status">
          {object.status ||
            "ACTIVE"}
        </span>
      </div>

      <div className="context-section">
        <span>POSITION</span>

        <div className="coordinate-value">
          {coordinates
            ? `${coordinates[0].toFixed(
                4
              )}°, ${coordinates[1].toFixed(
                4
              )}°`
            : "Unavailable"}
        </div>
      </div>

      {object.objectType ===
        "VEHICLE" && (
        <div className="context-section">
          <span>VEHICLE</span>

          <div className="context-grid">
            <div>
              <small>
                Type
              </small>

              <strong>
                {object.vehicle_type ||
                  "—"}
              </strong>
            </div>

            <div>
              <small>
                Capacity
              </small>

              <strong>
                {object.capacity ||
                  "—"}{" "}
                {object.capacity_unit ||
                  ""}
              </strong>
            </div>
          </div>
        </div>
      )}

      {object.location_type && (
        <div className="context-section">
          <span>LOCATION</span>

          <div className="context-grid">
            <div>
              <small>
                Name
              </small>

              <strong>
                {object.name ||
                  "—"}
              </strong>
            </div>

            <div>
              <small>
                Type
              </small>

              <strong>
                {
                  object.location_type
                }
              </strong>
            </div>
          </div>
        </div>
      )}

      <div className="context-section">
        <span>NETWORK</span>

        <div className="network-summary">
          <div>
            <strong>
              {inventory.length}
            </strong>

            <small>
              Inventory
            </small>
          </div>

          <div>
            <strong>
              {shipments.length}
            </strong>

            <small>
              Shipments
            </small>
          </div>
        </div>
      </div>

      {depotCoordinates &&
        forwardCoordinates && (
          <div className="route-context">
            <div>
              <small>
                PRIMARY CORRIDOR
              </small>

              <strong>
                {depot?.code ||
                  "DEPOT"}{" "}
                →{" "}
                {forwardBase?.code ||
                  "FORWARD"}
              </strong>
            </div>

            <span className="route-status">
              CONNECTED
            </span>
          </div>
        )}
    </aside>
  );
}

/* =========================================================
   MOVEMENT
   ========================================================= */

function MovementView({
  shipments,
  vehicles,
}) {
  return (
    <section className="secondary-view">
      <div className="view-heading">
        <div>
          <span className="eyebrow">
            MOVEMENT INTELLIGENCE
          </span>

          <h2>
            Transport Network
          </h2>

          <p>
            Track planned and
            completed logistics
            movements across the
            operational network.
          </p>
        </div>
      </div>

      <div className="summary-grid">
        <LargeMetric
          title="Total Shipments"
          value={shipments.length}
        />

        <LargeMetric
          title="Vehicles"
          value={vehicles.length}
        />

        <LargeMetric
          title="Available"
          value={
            vehicles.filter(
              (vehicle) =>
                vehicle.status ===
                "AVAILABLE"
            ).length
          }
        />
      </div>

      <div className="data-panel">
        <div className="panel-title">
          RECENT MOVEMENTS
        </div>

        {shipments
          .slice(0, 10)
          .map((shipment) => (
            <div
              className="movement-row"
              key={shipment.id}
            >
              <strong>
                {shipment.shipment_code ||
                  shipment.code ||
                  "Shipment"}
              </strong>

              <span>
                {shipment.source_location_code ||
                  "SOURCE"}{" "}
                →{" "}
                {shipment.destination_location_code ||
                  "DESTINATION"}
              </span>

              <span className="movement-status">
                {shipment.status ||
                  "UNKNOWN"}
              </span>
            </div>
          ))}
      </div>
    </section>
  );
}

/* =========================================================
   SUPPLY
   ========================================================= */

function SupplyView({
  inventory,
  locations,
}) {
  const belowMinimum =
    inventory.filter(
      (item) =>
        Number(item.quantity) <
        Number(
          item.minimum_stock
        )
    ).length;

  return (
    <section className="secondary-view">
      <div className="view-heading">
        <div>
          <span className="eyebrow">
            SUPPLY NETWORK
          </span>

          <h2>
            Inventory Readiness
          </h2>

          <p>
            Monitor inventory
            positions against
            configured stock
            thresholds.
          </p>
        </div>
      </div>

      <div className="summary-grid">
        <LargeMetric
          title="Tracked Positions"
          value={inventory.length}
        />

        <LargeMetric
          title="Locations"
          value={locations.length}
        />

        <LargeMetric
          title="Below Minimum"
          value={belowMinimum}
        />
      </div>

      <div className="data-panel">
        <div className="panel-title">
          INVENTORY POSITIONS
        </div>

        {inventory.map((item) => {
          const low =
            Number(item.quantity) <
            Number(
              item.minimum_stock
            );

          return (
            <div
              className="movement-row"
              key={item.id}
            >
              <strong>
                {item.item_code} ·{" "}
                {item.item_name}
              </strong>

              <span>
                {item.location_code} ·{" "}
                {item.quantity}{" "}
                {item.unit || ""}
              </span>

              <span
                className={
                  low
                    ? "risk-status"
                    : "healthy-status"
                }
              >
                {low
                  ? "LOW STOCK"
                  : "HEALTHY"}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/* =========================================================
   INTELLIGENCE
   ========================================================= */

function IntelligenceView() {
  return (
    <section className="secondary-view">
      <div className="view-heading">
        <div>
          <span className="eyebrow">
            DECISION INTELLIGENCE
          </span>

          <h2>
            AI Logistics Assessment
          </h2>

          <p>
            Forecasts, risk signals
            and optimization
            recommendations from
            the AI layer.
          </p>
        </div>
      </div>

      <div className="intelligence-grid">
        <div className="insight-card">
          <span className="eyebrow">
            SUPPLY RISK
          </span>

          <h3>Low</h3>

          <p>
            Current synthetic
            operational data
            indicates sufficient
            stock coverage for the
            active planning
            scenario.
          </p>
        </div>

        <div className="insight-card">
          <span className="eyebrow">
            MOVEMENT RISK
          </span>

          <h3>Review</h3>

          <p>
            ETA and route
            intelligence will
            surface delayed or
            incompatible movements
            here.
          </p>
        </div>

        <div className="insight-card">
          <span className="eyebrow">
            AI EXPLANATION
          </span>

          <h3>Why?</h3>

          <p>
            Recommendations expose
            the data, forecast and
            constraints influencing
            each decision.
          </p>
        </div>
      </div>
    </section>
  );
}

/* =========================================================
   DATA
   ========================================================= */

function DataView({
  gisData,
  inventory,
  vehicles,
  shipments,
}) {
  return (
    <section className="secondary-view">
      <div className="view-heading">
        <div>
          <span className="eyebrow">
            DATA OBSERVATORY
          </span>

          <h2>
            Operational Data Health
          </h2>

          <p>
            Unified view of
            information feeding the
            logistics picture.
          </p>
        </div>
      </div>

      <div className="summary-grid">
        <LargeMetric
          title="Locations"
          value={
            gisData?.locations
              ?.length || 0
          }
        />

        <LargeMetric
          title="Vehicles"
          value={vehicles.length}
        />

        <LargeMetric
          title="Inventory"
          value={inventory.length}
        />

        <LargeMetric
          title="Shipments"
          value={shipments.length}
        />
      </div>

      <div className="data-panel">
        <div className="panel-title">
          DATA LAYERS
        </div>

        <div className="movement-row">
          <strong>
            GIS Operational Layer
          </strong>

          <span>
            Locations · Vehicles ·
            Shipments
          </span>

          <span className="healthy-status">
            CONNECTED
          </span>
        </div>

        <div className="movement-row">
          <strong>
            Inventory Layer
          </strong>

          <span>
            Canonical logistics
            database
          </span>

          <span className="healthy-status">
            CONNECTED
          </span>
        </div>

        <div className="movement-row">
          <strong>
            AI Intelligence
          </strong>

          <span>
            Forecast · ETA · Risk ·
            Optimization
          </span>

          <span className="healthy-status">
            CONNECTED
          </span>
        </div>
      </div>
    </section>
  );
}

function LargeMetric({
  title,
  value,
}) {
  return (
    <div className="large-metric">
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

/* =========================================================
   COMMAND PALETTE
   ========================================================= */

function CommandPalette({
  close,
  selectView,
}) {
  const commands = [
    [
      "operations",
      "Operational Picture",
    ],
    [
      "movement",
      "Movement Intelligence",
    ],
    [
      "supply",
      "Supply Network",
    ],
    [
      "intelligence",
      "Decision Intelligence",
    ],
    [
      "data",
      "Data Observatory",
    ],
  ];

  return (
    <div
      className="command-overlay"
      onClick={close}
    >
      <div
        className="command-palette"
        onClick={(event) =>
          event.stopPropagation()
        }
      >
        <div className="command-search">
          <span>⌘</span>

          <input
            autoFocus
            placeholder="Go to operational view..."
          />
        </div>

        <div className="command-list">
          {commands.map(
            ([id, label]) => (
              <button
                key={id}
                onClick={() =>
                  selectView(id)
                }
              >
                <span>
                  {label}
                </span>

                <small>
                  Open
                </small>
              </button>
            )
          )}
        </div>
      </div>
    </div>
  );
}

export default App;