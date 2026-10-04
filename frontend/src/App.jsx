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

async function fetchJson(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = localStorage.getItem("predictive_logistics_access_token");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(url, { ...options, headers });

  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {}
    throw new Error(message);
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

          <button
            className={activeView === "logistics" ? "active" : ""}
            onClick={() => selectView("logistics")}
          >
            <span className="nav-icon">OPS</span>
            <small>Logistics</small>
          </button>

          <button
            className={activeView === "optimization" ? "active" : ""}
            onClick={() => selectView("optimization")}
          >
            <span className="nav-icon">OPT</span>
            <small>Optimize</small>
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

              {activeView === "logistics" &&
                "Logistics Management"}

              {activeView === "optimization" &&
                "Optimization & What-if"}
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
          <DataWorkspace
            gisData={gisData}
            inventory={inventory}
            vehicles={vehicles}
            shipments={shipments}
          />
        )}

        {activeView === "logistics" && (
          <LogisticsView onRefresh={loadOperationalData} />
        )}

        {activeView === "optimization" && (
          <OptimizationView
            inventory={inventory}
            locations={locations}
            vehicles={vehicles}
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
  const [items, setItems] = useState([]);
  const [locations, setLocations] = useState([]);
  const [shipments, setShipments] = useState([]);
  const [itemId, setItemId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [shipmentId, setShipmentId] = useState("");
  const [result, setResult] = useState(null);
  const [eta, setEta] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetchJson(`${API_URL}/api/logistics/items`),
      fetchJson(`${API_URL}/api/logistics/locations`),
      fetchJson(`${API_URL}/api/logistics/shipments`),
    ]).then(([i, l, s]) => {
      const nextItems = i.items || [];
      const nextLocations = l.locations || [];
      const nextShipments = s.shipments || [];
      setItems(nextItems);
      setLocations(nextLocations);
      setShipments(nextShipments);
      setItemId(nextItems[0]?.id || "");
      setLocationId(nextLocations[0]?.id || "");
      setShipmentId(nextShipments[0]?.id || "");
    }).catch((err) => setError(err.message));
  }, []);

  async function runAssessment() {
    if (!itemId || !locationId) {
      setError("Select an item and location.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [forecast, stockout, risk, anomaly, reliability, explanation] = await Promise.all([
        fetchJson(`${API_URL}/api/ai/forecast/${itemId}/${locationId}`),
        fetchJson(`${API_URL}/api/ai/stockout/${itemId}/${locationId}`),
        fetchJson(`${API_URL}/api/ai/risk/${itemId}/${locationId}`),
        fetchJson(`${API_URL}/api/ai/anomaly/${itemId}/${locationId}`),
        fetchJson(`${API_URL}/api/ai/reliability/${itemId}/${locationId}`),
        fetchJson(`${API_URL}/api/ai/risk/${itemId}/${locationId}/explanation`),
      ]);
      setResult({ forecast, stockout, risk, anomaly, reliability, explanation });
      if (shipmentId) {
        try {
          setEta(await fetchJson(`${API_URL}/api/ai/eta/${shipmentId}`));
        } catch {
          setEta(null);
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const unwrap = (payload, key) => payload?.[key] ?? payload?.result ?? payload?.data ?? payload;
  const forecast = unwrap(result?.forecast, "forecast");
  const stockout = unwrap(result?.stockout, "stockout");
  const risk = unwrap(result?.risk, "risk");
  const reliability = unwrap(result?.reliability, "reliability");

  return (
    <section className="secondary-view">
      <div className="view-heading">
        <div>
          <span className="eyebrow">DECISION INTELLIGENCE</span>
          <h2>AI logistics assessment</h2>
          <p>Run the existing forecasting, stockout, risk, anomaly, ETA and explainability services against live canonical data.</p>
        </div>
      </div>

      {error && <div className="hub-alert hub-alert-error">{error}</div>}

      <div className="data-panel ai-control-panel">
        <div className="panel-title">ASSESSMENT TARGET</div>
        <div className="form-grid-3">
          <label className="hub-field"><span>Item</span><select value={itemId} onChange={(e) => setItemId(e.target.value)}>{items.map((item) => <option key={item.id} value={item.id}>{item.item_code} · {item.name}</option>)}</select></label>
          <label className="hub-field"><span>Location</span><select value={locationId} onChange={(e) => setLocationId(e.target.value)}>{locations.map((location) => <option key={location.id} value={location.id}>{location.code} · {location.name}</option>)}</select></label>
          <label className="hub-field"><span>Shipment for ETA</span><select value={shipmentId} onChange={(e) => setShipmentId(e.target.value)}><option value="">No shipment</option>{shipments.map((shipment) => <option key={shipment.id} value={shipment.id}>{shipment.shipment_code}</option>)}</select></label>
        </div>
        <button className="hub-primary-button" type="button" onClick={runAssessment} disabled={loading}>{loading ? "Running AI assessment..." : "Run AI assessment →"}</button>
      </div>

      {result && (
        <>
          <div className="summary-grid">
            <LargeMetric title="Forecast" value={`${Number(forecast?.predicted_quantity ?? forecast?.forecast_quantity ?? 0).toFixed(1)}`} />
            <LargeMetric title="Stockout risk" value={stockout?.risk_level || risk?.risk_level || "—"} />
            <LargeMetric title="Risk score" value={risk?.risk_score != null ? Number(risk.risk_score).toFixed(1) : "—"} />
            <LargeMetric title="Model reliability" value={reliability?.reliability_level || reliability?.level || "—"} />
          </div>
          <div className="ai-result-grid">
            <div className="data-panel"><div className="panel-title">FORECAST</div><pre className="json-result">{JSON.stringify(result.forecast, null, 2)}</pre></div>
            <div className="data-panel"><div className="panel-title">RISK + STOCKOUT</div><pre className="json-result">{JSON.stringify({ stockout: result.stockout, risk: result.risk }, null, 2)}</pre></div>
            <div className="data-panel"><div className="panel-title">WHY?</div><pre className="json-result">{JSON.stringify(result.explanation, null, 2)}</pre></div>
            <div className="data-panel"><div className="panel-title">ANOMALY + RELIABILITY</div><pre className="json-result">{JSON.stringify({ anomaly: result.anomaly, reliability: result.reliability, eta }, null, 2)}</pre></div>
          </div>
        </>
      )}
    </section>
  );
}


function DataWorkspace(props) {
  const [tab, setTab] = useState("hub");
  return (
    <section className="secondary-view data-workspace">
      <div className="workspace-switcher">
        <button className={tab === "hub" ? "active" : ""} onClick={() => setTab("hub")}>Data Hub</button>
        <button className={tab === "observatory" ? "active" : ""} onClick={() => setTab("observatory")}>Data Observatory</button>
      </div>
      {tab === "hub" ? <DataHubView {...props} /> : <DataView {...props} />}
    </section>
  );
}

function LogisticsView({ onRefresh }) {
  const [tab, setTab] = useState("inventory");
  const [items, setItems] = useState([]);
  const [locations, setLocations] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [shipments, setShipments] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState({});

  async function load() {
    try {
      const [i, l, inv, v, s] = await Promise.all([
        fetchJson(`${API_URL}/api/logistics/items`),
        fetchJson(`${API_URL}/api/logistics/locations`),
        fetchJson(`${API_URL}/api/logistics/inventory`),
        fetchJson(`${API_URL}/api/logistics/vehicles`),
        fetchJson(`${API_URL}/api/logistics/shipments`),
      ]);
      setItems(i.items || []); setLocations(l.locations || []); setInventory(inv.inventory || []); setVehicles(v.vehicles || []); setShipments(s.shipments || []);
    } catch (err) { setError(err.message); }
  }
  useEffect(() => { load(); }, []);

  function setField(key, value) { setForm((current) => ({ ...current, [key]: value })); }
  async function create(path, payload, success) {
    setError(""); setMessage("");
    try {
      await fetchJson(`${API_URL}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setMessage(success); setForm({}); await load(); if (onRefresh) onRefresh();
    } catch (err) { setError(err.message); }
  }

  const commonTabs = ["inventory", "items", "locations", "vehicles", "shipments"];
  return (
    <section className="secondary-view">
      <div className="view-heading"><div><span className="eyebrow">LOGISTICS MANAGEMENT</span><h2>Operational records</h2><p>Create and inspect the canonical logistics records consumed by GIS, AI and optimization.</p></div></div>
      {message && <div className="hub-alert hub-alert-success">{message}</div>}
      {error && <div className="hub-alert hub-alert-error">{error}</div>}
      <div className="workspace-switcher">{commonTabs.map((name) => <button key={name} className={tab === name ? "active" : ""} onClick={() => { setTab(name); setForm({}); }}>{name}</button>)}</div>

      {tab === "inventory" && <>
        <div className="data-panel"><div className="panel-title">ADD INVENTORY POSITION</div><div className="form-grid-3">
          <label className="hub-field"><span>Item</span><select value={form.item_id || ""} onChange={(e) => setField("item_id", e.target.value)}><option value="">Select item</option>{items.map((x) => <option key={x.id} value={x.id}>{x.item_code} · {x.name}</option>)}</select></label>
          <label className="hub-field"><span>Location</span><select value={form.location_id || ""} onChange={(e) => setField("location_id", e.target.value)}><option value="">Select location</option>{locations.map((x) => <option key={x.id} value={x.id}>{x.code}</option>)}</select></label>
          <label className="hub-field"><span>Quantity</span><input type="number" min="0" value={form.quantity || ""} onChange={(e) => setField("quantity", Number(e.target.value))}/></label>
          <label className="hub-field"><span>Minimum stock</span><input type="number" min="0" value={form.minimum_stock || ""} onChange={(e) => setField("minimum_stock", Number(e.target.value))}/></label>
          <label className="hub-field"><span>Maximum stock</span><input type="number" min="0" value={form.maximum_stock || ""} onChange={(e) => setField("maximum_stock", Number(e.target.value))}/></label>
        </div><button className="hub-primary-button" onClick={() => create("/api/logistics/inventory", { item_id: form.item_id, location_id: form.location_id, quantity: Number(form.quantity || 0), minimum_stock: Number(form.minimum_stock || 0), maximum_stock: form.maximum_stock === "" || form.maximum_stock == null ? null : Number(form.maximum_stock) }, "Inventory position created.")}>Add inventory →</button></div>
        <RecordTable title="CURRENT INVENTORY" columns={["item_code", "item_name", "location_code", "quantity", "minimum_stock"]} rows={inventory}/>
      </>}

      {tab === "items" && <>
        <SimpleCreate title="ADD ITEM" fields={[['item_code','Item code'],['name','Name'],['category','Category'],['unit','Unit']]} form={form} setField={setField} onSubmit={() => create("/api/logistics/items", { item_code: form.item_code, name: form.name, category: form.category || null, unit: form.unit || "UNIT" }, "Item created.")} />
        <RecordTable title="ITEM MASTER" columns={["item_code", "name", "category", "unit"]} rows={items}/>
      </>}

      {tab === "locations" && <>
        <SimpleCreate title="ADD LOCATION" fields={[['code','Code'],['name','Name'],['location_type','Type'],['latitude','Latitude'],['longitude','Longitude']]} form={form} setField={setField} onSubmit={() => create("/api/logistics/locations", { code: form.code, name: form.name, location_type: form.location_type || "DEPOT", latitude: Number(form.latitude), longitude: Number(form.longitude) }, "Location created.")} />
        <RecordTable title="LOCATIONS" columns={["code", "name", "location_type", "is_active"]} rows={locations}/>
      </>}

      {tab === "vehicles" && <>
        <SimpleCreate title="ADD VEHICLE" fields={[['vehicle_code','Vehicle code'],['vehicle_type','Type'],['capacity','Capacity'],['capacity_unit','Capacity unit'],['status','Status']]} form={form} setField={setField} onSubmit={() => create("/api/logistics/vehicles", { vehicle_code: form.vehicle_code, vehicle_type: form.vehicle_type, capacity: Number(form.capacity), capacity_unit: form.capacity_unit || "UNIT", status: form.status || "AVAILABLE", current_location_id: form.current_location_id || null }, "Vehicle created.")} extra={<label className="hub-field"><span>Current location</span><select value={form.current_location_id || ""} onChange={(e) => setField("current_location_id", e.target.value)}><option value="">None</option>{locations.map((x) => <option key={x.id} value={x.id}>{x.code}</option>)}</select></label>} />
        <RecordTable title="VEHICLE FLEET" columns={["vehicle_code", "vehicle_type", "capacity", "capacity_unit", "status"]} rows={vehicles}/>
      </>}

      {tab === "shipments" && <>
        <SimpleCreate title="ADD SHIPMENT" fields={[['shipment_code','Shipment code'],['quantity','Quantity'],['status','Status']]} form={form} setField={setField} extra={<><label className="hub-field"><span>Item</span><select value={form.item_id || ""} onChange={(e) => setField("item_id", e.target.value)}><option value="">Select</option>{items.map((x) => <option key={x.id} value={x.id}>{x.item_code}</option>)}</select></label><label className="hub-field"><span>Source</span><select value={form.source_location_id || ""} onChange={(e) => setField("source_location_id", e.target.value)}><option value="">Select</option>{locations.map((x) => <option key={x.id} value={x.id}>{x.code}</option>)}</select></label><label className="hub-field"><span>Destination</span><select value={form.destination_location_id || ""} onChange={(e) => setField("destination_location_id", e.target.value)}><option value="">Select</option>{locations.map((x) => <option key={x.id} value={x.id}>{x.code}</option>)}</select></label><label className="hub-field"><span>Vehicle</span><select value={form.vehicle_id || ""} onChange={(e) => setField("vehicle_id", e.target.value)}><option value="">None</option>{vehicles.map((x) => <option key={x.id} value={x.id}>{x.vehicle_code}</option>)}</select></label></>} onSubmit={() => create("/api/logistics/shipments", { shipment_code: form.shipment_code, item_id: form.item_id, quantity: Number(form.quantity), source_location_id: form.source_location_id, destination_location_id: form.destination_location_id, vehicle_id: form.vehicle_id || null, status: form.status || "PLANNED" }, "Shipment created.")} />
        <RecordTable title="SHIPMENTS" columns={["shipment_code", "item_code", "quantity", "source_location_code", "destination_location_code", "status"]} rows={shipments}/>
      </>}
    </section>
  );
}

function SimpleCreate({ title, fields, form, setField, onSubmit, extra }) {
  return <div className="data-panel"><div className="panel-title">{title}</div><div className="form-grid-3">{fields.map(([key, label]) => <label className="hub-field" key={key}><span>{label}</span><input value={form[key] ?? ""} onChange={(e) => setField(key, e.target.value)} /></label>)}{extra}</div><button className="hub-primary-button" type="button" onClick={onSubmit}>Create →</button></div>;
}

function RecordTable({ title, columns, rows }) {
  return <div className="data-panel record-table-panel"><div className="panel-title">{title}</div><div className="record-table"><div className="record-row record-head">{columns.map((c) => <span key={c}>{c.replaceAll('_',' ')}</span>)}</div>{rows.slice(0, 25).map((row, index) => <div className="record-row" key={row.id || index}>{columns.map((c) => <span key={c}>{String(row[c] ?? "—")}</span>)}</div>)}</div></div>;
}

function OptimizationView({ inventory, locations, vehicles }) {
  const [selectedInventory, setSelectedInventory] = useState(inventory[0]?.id || "");
  const [destination, setDestination] = useState("");
  const [additionalSupply, setAdditionalSupply] = useState(0);
  const [demandChange, setDemandChange] = useState(0);
  const [routeAvailable, setRouteAvailable] = useState(true);
  const [routeRisk, setRouteRisk] = useState("LOW");
  const [vehicleId, setVehicleId] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (!selectedInventory && inventory[0]) setSelectedInventory(inventory[0].id); }, [inventory, selectedInventory]);
  const current = inventory.find((x) => x.id === selectedInventory) || inventory[0];

  async function runScenario() {
    if (!current) { setError("No inventory position is available."); return; }
    setLoading(true); setError("");
    try {
      const payload = { item_id: current.item_id, location_id: current.location_id, additional_supply: Number(additionalSupply || 0), demand_change_percent: Number(demandChange || 0), vehicle_id: vehicleId || null, destination_location_id: destination || null, route_available: routeAvailable, route_risk_level: routeRisk };
      setResult(await fetchJson(`${API_URL}/api/optimization/what-if/operational`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }

  return <section className="secondary-view"><div className="view-heading"><div><span className="eyebrow">OPTIMIZATION ENGINE</span><h2>Plan, compare, decide.</h2><p>Run a non-destructive operational scenario using the existing resupply, vehicle, route and demand constraints.</p></div></div>
    {error && <div className="hub-alert hub-alert-error">{error}</div>}
    <div className="data-panel"><div className="panel-title">WHAT-IF SCENARIO</div><div className="form-grid-3">
      <label className="hub-field"><span>Inventory position</span><select value={selectedInventory} onChange={(e) => setSelectedInventory(e.target.value)}>{inventory.map((x) => <option key={x.id} value={x.id}>{x.item_code} · {x.location_code} · {x.quantity}</option>)}</select></label>
      <label className="hub-field"><span>Destination context</span><select value={destination} onChange={(e) => setDestination(e.target.value)}><option value="">No destination</option>{locations.map((x) => <option key={x.id} value={x.id}>{x.code}</option>)}</select></label>
      <label className="hub-field"><span>Vehicle</span><select value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}><option value="">Auto / none</option>{vehicles.map((x) => <option key={x.id} value={x.id}>{x.vehicle_code}</option>)}</select></label>
      <label className="hub-field"><span>Additional supply</span><input type="number" value={additionalSupply} onChange={(e) => setAdditionalSupply(e.target.value)} /></label>
      <label className="hub-field"><span>Demand change %</span><input type="number" value={demandChange} onChange={(e) => setDemandChange(e.target.value)} /></label>
      <label className="hub-field"><span>Route risk</span><select value={routeRisk} onChange={(e) => setRouteRisk(e.target.value)}><option>LOW</option><option>MEDIUM</option><option>HIGH</option></select></label>
      <label className="hub-field"><span>Route available</span><select value={String(routeAvailable)} onChange={(e) => setRouteAvailable(e.target.value === "true")}><option value="true">Available</option><option value="false">Unavailable</option></select></label>
    </div><button className="hub-primary-button" onClick={runScenario} disabled={loading}>{loading ? "Calculating..." : "Run scenario →"}</button></div>
    {result && <div className="ai-result-grid"><div className="data-panel"><div className="panel-title">DECISION</div><h3 className="decision-heading">{result.scenario?.decision || "—"}</h3><p>{result.scenario?.decision_reason || result.scenario?.explanation || ""}</p><div className="constraint-list">{(result.constraints || []).map((c) => <div key={c.code} className={c.passed ? "constraint-pass" : "constraint-fail"}>{c.passed ? "✓" : "!"} {c.code}: {c.message}</div>)}</div></div><div className="data-panel"><div className="panel-title">BASELINE VS SCENARIO</div>{(result.comparisons || []).map((c) => <div className="comparison-row" key={c.metric}><span>{c.metric}</span><strong>{Number(c.baseline_value ?? 0).toFixed(2)} → {Number(c.scenario_value ?? 0).toFixed(2)}</strong><small>{c.change_percent == null ? "" : `${Number(c.change_percent).toFixed(1)}%`}</small></div>)}</div></div>}
  </section>;
}

/* =========================================================
   DATA HUB
   ========================================================= */

function DataHubView({
  gisData,
  inventory,
  vehicles,
  shipments,
}) {
  const [sources, setSources] = useState([]);
  const [activeTab, setActiveTab] = useState("sources");
  const [loadingSources, setLoadingSources] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [selectedSource, setSelectedSource] = useState(null);
  const [sourceDetails, setSourceDetails] = useState(null);
  const [history, setHistory] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [validationResult, setValidationResult] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadCategory, setUploadCategory] = useState("CUSTOM");
  const [uploadResult, setUploadResult] = useState(null);
  const [assistantResult, setAssistantResult] = useState(null);
  const [assistantOverrides, setAssistantOverrides] = useState({});
  const [mappingName, setMappingName] = useState("Data Assistant confirmed mapping");
  const [registration, setRegistration] = useState({
    name: "",
    source_type: "DATABASE",
    data_category: "CUSTOM",
    description: "",
    host: "",
    port: "5432",
    database: "",
    username: "",
    api_url: "",
    api_method: "GET",
    protocol: "MQTT",
    device_endpoint: "",
  });

  async function loadSources() {
    setLoadingSources(true);
    setError("");
    try {
      const payload = await fetchJson(
        `${API_URL}/api/management/sources`
      );
      setSources(payload.sources || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingSources(false);
    }
  }

  useEffect(() => {
    loadSources();
  }, []);

  async function openSource(source) {
    setSelectedSource(source);
    setError("");
    try {
      const [details, historyResponse, mappingResponse] =
        await Promise.all([
          fetchJson(`${API_URL}/api/management/sources/${source.id}`),
          fetchJson(`${API_URL}/api/management/sources/${source.id}/ingestion-history`),
          fetchJson(`${API_URL}/api/management/sources/${source.id}/mappings`),
        ]);
      setSourceDetails(details);
      setHistory(historyResponse.jobs || []);
      setMappings(mappingResponse.mappings || []);
    } catch (err) {
      setError(err.message);
    }
  }

  function updateRegistration(field, value) {
    setRegistration((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function handleUpload(event) {
    event.preventDefault();
    if (!uploadFile) {
      setError("Select a CSV, JSON, XLSX or PDF file first.");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    setUploadResult(null);

    try {
      const formData = new FormData();
      formData.append("file", uploadFile);

      const response = await fetch(`${API_URL}/api/ingestion/upload`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("predictive_logistics_access_token") || ""}`,
        },
        body: formData,
      });

      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.detail || `Upload failed: ${response.status}`);
      }

      setUploadResult(payload);
      setMessage(`Uploaded ${payload.filename}. The source is now available in the Data Hub.`);
      setUploadFile(null);
      await loadSources();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function registerSource(event) {
    event.preventDefault();
    if (!registration.name.trim()) {
      setError("Source name is required.");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");

    try {
      const config = {
        registration_mode: "frontend_data_hub",
      };

      if (registration.source_type === "DATABASE") {
        Object.assign(config, {
          host: registration.host,
          port: registration.port,
          database: registration.database,
          username: registration.username,
        });
      }

      if (registration.source_type === "API") {
        Object.assign(config, {
          url: registration.api_url,
          method: registration.api_method,
        });
      }

      if (registration.source_type === "DEVICE") {
        Object.assign(config, {
          protocol: registration.protocol,
          endpoint: registration.device_endpoint,
        });
      }

      if (registration.source_type === "MANUAL") {
        config.entry_mode = "manual";
      }

      const response = await fetch(`${API_URL}/api/management/sources`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("predictive_logistics_access_token") || ""}`,
        },
        body: JSON.stringify({
          name: registration.name.trim(),
          source_type: registration.source_type,
          data_category: registration.data_category,
          description: registration.description.trim() || null,
          config,
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Source registration failed: ${response.status}`);
      }

      setMessage(`Source registered: ${payload.name}`);
      setRegistration({
        name: "",
        source_type: "DATABASE",
        data_category: "CUSTOM",
        description: "",
        host: "",
        port: "5432",
        database: "",
        username: "",
        api_url: "",
        api_method: "GET",
        protocol: "MQTT",
        device_endpoint: "",
      });
      await loadSources();
      setActiveTab("sources");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function runValidation(ingestionJobId) {
    if (!ingestionJobId) {
      setError("No ingestion job is available for validation.");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    setValidationResult(null);

    try {
      const response = await fetch(
        `${API_URL}/api/ingestion/validate?ingestion_job_id=${encodeURIComponent(ingestionJobId)}`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${localStorage.getItem("predictive_logistics_access_token") || ""}`,
          },
        }
      );

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Validation failed: ${response.status}`);
      }

      setValidationResult(payload);
      setMessage(
        `Validation complete: ${payload.valid_records} valid, ${payload.quarantined_records} quarantined.`
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function runDataAssistant() {
    if (!selectedSource) {
      setError("Select a tabular file source first.");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch(
        `${API_URL}/api/ingestion/assistant?source_id=${selectedSource.id}`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${localStorage.getItem("predictive_logistics_access_token") || ""}`,
          },
        }
      );

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail?.message || payload.detail || `Data Assistant failed: ${response.status}`);
      }

      setAssistantResult(payload);
      const initialOverrides = {};
      (payload.suggestions || []).forEach((item) => {
        initialOverrides[item.column] = item.suggested_field || "";
      });
      setAssistantOverrides(initialOverrides);
      setActiveTab("assistant");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function confirmAssistantMapping() {
    if (!selectedSource || !assistantResult) return;

    setBusy(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch(`${API_URL}/api/ingestion/confirm-mapping`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("predictive_logistics_access_token") || ""}`,
        },
        body: JSON.stringify({
          source_id: selectedSource.id,
          name: mappingName.trim() || "Data Assistant confirmed mapping",
          overrides: Object.fromEntries(
            Object.entries(assistantOverrides).map(([column, field]) => [column, field || null])
          ),
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        const detail = payload.detail;
        const conflictText = detail?.conflicts
          ? ` Conflicts: ${detail.conflicts.map((item) => item.message).join(" | ")}`
          : "";
        throw new Error((detail?.message || detail || `Mapping confirmation failed: ${response.status}`) + conflictText);
      }

      setMessage(`Mapping saved successfully as version ${payload.version}.`);
      await openSource(selectedSource);
      setActiveTab("sources");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const sourceTypeLabel = (type) =>
    ({
      FILE: "File",
      API: "Online API",
      DATABASE: "Database",
      DEVICE: "Device / Sensor",
      MANUAL: "Manual",
    }[type] || type);

  return (
    <section className="secondary-view data-hub-view">
      <div className="view-heading data-hub-heading">
        <div>
          <span className="eyebrow">UNIVERSAL DATA HUB</span>
          <h2>Connect the information that drives logistics.</h2>
          <p>
            Upload operational files, register existing systems and inspect the
            sources feeding the common logistics data layer.
          </p>
        </div>

        <div className="data-hub-actions">
          <button
            className="hub-secondary-button"
            type="button"
            onClick={() => {
              setActiveTab("upload");
              setError("");
            }}
          >
            + Upload data
          </button>
          <button
            className="hub-primary-button"
            type="button"
            onClick={() => {
              setActiveTab("register");
              setError("");
            }}
          >
            + Add data source
          </button>
        </div>
      </div>

      {message && <div className="hub-alert hub-alert-success">{message}</div>}
      {error && <div className="hub-alert hub-alert-error">{error}</div>}

      <div className="data-hub-summary">
        <LargeMetric title="Registered Sources" value={sources.length} />
        <LargeMetric title="Active" value={sources.filter((source) => source.status === "ACTIVE").length} />
        <LargeMetric title="File Sources" value={sources.filter((source) => source.source_type === "FILE").length} />
        <LargeMetric title="Operational Records" value={
          (gisData?.locations?.length || 0) + inventory.length + vehicles.length + shipments.length
        } />
      </div>

      <div className="data-hub-tabs">
        <button className={activeTab === "sources" ? "active" : ""} onClick={() => setActiveTab("sources")}>Sources</button>
        <button className={activeTab === "upload" ? "active" : ""} onClick={() => setActiveTab("upload")}>Upload file</button>
        <button className={activeTab === "register" ? "active" : ""} onClick={() => setActiveTab("register")}>Register system</button>
        <button className={activeTab === "assistant" ? "active" : ""} onClick={runDataAssistant} disabled={!selectedSource || busy}>Data Assistant</button>
      </div>

      {activeTab === "sources" && (
        <div className="data-hub-grid">
          <div className="data-panel source-list-panel">
            <div className="panel-header-row">
              <div>
                <div className="panel-title">CONNECTED SOURCES</div>
                <p className="panel-description">Every source registered in the platform.</p>
              </div>
              <button className="hub-icon-button" onClick={loadSources} disabled={loadingSources}>↻</button>
            </div>

            {loadingSources && <div className="hub-empty">Loading sources...</div>}

            {!loadingSources && sources.length === 0 && (
              <div className="hub-empty">
                <strong>No data sources yet.</strong>
                <span>Upload a file or register an existing system to begin.</span>
              </div>
            )}

            {!loadingSources && sources.map((source) => (
              <button
                className={`source-row ${selectedSource?.id === source.id ? "selected" : ""}`}
                key={source.id}
                onClick={() => openSource(source)}
              >
                <div className="source-type-badge">{source.source_type}</div>
                <div className="source-row-main">
                  <strong>{source.name}</strong>
                  <span>{sourceTypeLabel(source.source_type)} · {source.data_category}</span>
                </div>
                <div className="source-row-status">
                  <span className={`source-status-dot ${source.status === "ACTIVE" ? "active" : "error"}`} />
                  {source.status}
                </div>
              </button>
            ))}
          </div>

          <div className="data-panel source-detail-panel">
            {!selectedSource && (
              <div className="hub-detail-placeholder">
                <span className="hub-detail-icon">⌁</span>
                <strong>Select a source</strong>
                <p>Inspect configuration, ingestion history and saved mappings.</p>
              </div>
            )}

            {selectedSource && sourceDetails && (
              <>
                <div className="source-detail-header">
                  <div>
                    <span className="eyebrow">SOURCE DETAIL</span>
                    <h3>{sourceDetails.name}</h3>
                    <p>{sourceDetails.description || "No description provided."}</p>
                  </div>
                  <span className={`source-detail-state ${sourceDetails.status === "ACTIVE" ? "healthy" : "warning"}`}>
                    {sourceDetails.status}
                  </span>
                </div>

                <div className="source-detail-facts">
                  <div><span>TYPE</span><strong>{sourceDetails.source_type}</strong></div>
                  <div><span>CATEGORY</span><strong>{sourceDetails.data_category}</strong></div>
                  <div><span>SCHEMA</span><strong>{sourceDetails.schema_version}</strong></div>
                  <div><span>LAST SYNC</span><strong>{sourceDetails.last_sync_at ? new Date(sourceDetails.last_sync_at).toLocaleString() : "Never"}</strong></div>
                </div>

                <div className="source-detail-section">
                  <div className="panel-title">INGESTION HISTORY</div>
                  {history.length === 0 ? (
                    <p className="panel-description">No ingestion jobs recorded.</p>
                  ) : history.map((job) => (
                    <div className="history-row history-row-action" key={job.id}>
                      <div>
                        <strong>{job.status}</strong>
                        <span>{job.created_at ? new Date(job.created_at).toLocaleString() : "—"}</span>
                      </div>
                      <button
                        className="hub-small-button"
                        type="button"
                        onClick={() => runValidation(job.id)}
                        disabled={busy || String(job.status || "").toUpperCase() !== "COMPLETED"}
                      >
                        Validate
                      </button>
                    </div>
                  ))}
                </div>

                {validationResult && (
                  <div className="validation-result-card">
                    <div className="validation-result-header">
                      <div>
                        <div className="panel-title">VALIDATION RESULT</div>
                        <p className="panel-description">The active mapping was applied and every staged record was checked against the logistics validation rules.</p>
                      </div>
                      <span className={`validation-grade ${validationResult.quality_score >= 90 ? "good" : validationResult.quality_score >= 60 ? "watch" : "bad"}`}>
                        {Number(validationResult.quality_score ?? 0).toFixed(1)}%
                      </span>
                    </div>
                    <div className="validation-result-grid">
                      <div><span>TOTAL</span><strong>{validationResult.total_records}</strong></div>
                      <div><span>VALID</span><strong>{validationResult.valid_records}</strong></div>
                      <div><span>QUARANTINED</span><strong>{validationResult.quarantined_records}</strong></div>
                    </div>
                    {validationResult.results?.some((item) => !item.valid) && (
                      <div className="validation-errors-list">
                        <strong>Records requiring attention</strong>
                        {validationResult.results.filter((item) => !item.valid).slice(0, 10).map((item) => (
                          <div key={item.record_number} className="validation-error-row">
                            <span>Row {item.record_number}</span>
                            <span>{item.errors?.join(" · ") || "Validation failed"}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="source-detail-section">
                  <div className="panel-title">SAVED MAPPINGS</div>
                  {mappings.length === 0 ? (
                    <p className="panel-description">No mappings saved yet. Use Data Assistant after uploading a tabular file.</p>
                  ) : mappings.map((mapping) => (
                    <div className="history-row" key={mapping.id}>
                      <strong>{mapping.name} · v{mapping.version}</strong>
                      <span>{mapping.is_active ? "ACTIVE" : "ARCHIVED"}</span>
                    </div>
                  ))}
                </div>

                <div className="source-detail-assistant">
                  <div>
                    <div className="panel-title">DATA ASSISTANT</div>
                    <p className="panel-description">Analyze this upload, detect its schema and suggest canonical logistics fields with confidence.</p>
                  </div>
                  <button className="hub-primary-button" type="button" onClick={runDataAssistant} disabled={busy || sourceDetails.source_type !== "FILE"}>
                    {busy ? "Analyzing..." : "Analyze with Data Assistant →"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {activeTab === "upload" && (
        <div className="data-hub-grid upload-grid">
          <form className="data-panel upload-panel" onSubmit={handleUpload}>
            <div className="panel-title">UPLOAD OPERATIONAL DATA</div>
            <p className="panel-description">Supported: CSV, JSON, XLSX and PDF · maximum 10 MB.</p>

            <label className="hub-file-drop">
              <input
                type="file"
                accept=".csv,.json,.xlsx,.pdf"
                onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
              />
              <span className="file-drop-icon">↑</span>
              <strong>{uploadFile ? uploadFile.name : "Choose a file"}</strong>
              <small>{uploadFile ? `${(uploadFile.size / 1024).toFixed(1)} KB selected` : "Drop it here or browse from this computer"}</small>
            </label>

            <label className="hub-field">
              <span>What kind of information is this?</span>
              <select value={uploadCategory} onChange={(event) => setUploadCategory(event.target.value)}>
                <option value="CUSTOM">Let Data Assistant detect</option>
                <option value="INVENTORY">Inventory</option>
                <option value="CONSUMPTION">Daily Consumption</option>
                <option value="VEHICLES">Vehicles</option>
                <option value="SHIPMENTS">Shipments</option>
                <option value="LOCATIONS">Locations</option>
                <option value="ROUTES">Routes</option>
                <option value="WEATHER">Weather</option>
                <option value="DEMAND">Demand</option>
                <option value="MAINTENANCE">Maintenance</option>
              </select>
            </label>

            <button className="hub-primary-button wide" disabled={busy || !uploadFile} type="submit">
              {busy ? "Processing..." : "Upload and stage data →"}
            </button>
          </form>

          <div className="data-panel upload-result-panel">
            <div className="panel-title">INGESTION RESULT</div>
            {!uploadResult ? (
              <div className="hub-detail-placeholder compact">
                <strong>Ready for a file</strong>
                <p>The platform will create a source, ingestion job and staging records automatically.</p>
              </div>
            ) : (
              <>
                <div className="upload-success-summary">
                  <span>✓</span>
                  <div><strong>{uploadResult.filename}</strong><small>{uploadResult.staged_record_count ?? uploadResult.row_count ?? 1} records staged</small></div>
                </div>
                {uploadResult.columns && <div className="column-list">{uploadResult.columns.map((column) => <span key={column}>{column}</span>)}</div>}
                {uploadResult.preview && <pre className="preview-box">{JSON.stringify(uploadResult.preview, null, 2)}</pre>}
              </>
            )}
          </div>
        </div>
      )}

      {activeTab === "assistant" && (
        <div className="assistant-workspace">
          {!assistantResult ? (
            <div className="data-panel hub-detail-placeholder">
              <strong>Select a file source and run Data Assistant.</strong>
              <p>The assistant will inspect staged records and classify every column as AUTO, SUGGEST or REVIEW.</p>
            </div>
          ) : (
            <>
              <div className="data-hub-summary assistant-summary">
                <LargeMetric title="Columns" value={assistantResult.summary?.total_columns || 0} />
                <LargeMetric title="Auto mapped" value={assistantResult.summary?.auto_mapped || 0} />
                <LargeMetric title="Suggestions" value={assistantResult.summary?.suggestions || 0} />
                <LargeMetric title="Needs review" value={assistantResult.summary?.needs_review || 0} />
              </div>

              <div className="data-panel assistant-panel">
                <div className="panel-header-row">
                  <div>
                    <div className="panel-title">SCHEMA MAPPING REVIEW</div>
                    <p className="panel-description">High-confidence fields are preselected. Review uncertain fields before saving the mapping.</p>
                  </div>
                  <span className={`assistant-confidence ${assistantResult.summary?.needs_review ? "warning" : "healthy"}`}>
                    {assistantResult.summary?.needs_review ? "REVIEW REQUIRED" : "READY TO CONFIRM"}
                  </span>
                </div>

                <div className="assistant-table">
                  <div className="assistant-row assistant-row-head">
                    <span>Source column</span><span>Suggested field</span><span>Confidence</span><span>Decision</span>
                  </div>
                  {(assistantResult.suggestions || []).map((item) => (
                    <div className="assistant-row" key={item.column}>
                      <div><strong>{item.column}</strong><small>{item.sample_values?.slice(0, 3).map(String).join(" · ") || "No sample values"}</small></div>
                      <select value={assistantOverrides[item.column] ?? ""} onChange={(event) => setAssistantOverrides((current) => ({ ...current, [item.column]: event.target.value }))}>
                        <option value="">— Leave unmapped —</option>
                        {assistantResult.suggestions.flatMap((entry) => entry.candidates || []).map((candidate) => candidate.field).filter((field, index, fields) => fields.indexOf(field) === index).map((field) => <option key={field} value={field}>{field}</option>)}
                      </select>
                      <span className="confidence-value">{Math.round((item.confidence || 0) * 100)}%</span>
                      <span className={`assistant-decision ${item.decision.toLowerCase()}`}>{item.decision}</span>
                    </div>
                  ))}
                </div>

                {assistantResult.conflicts?.length > 0 && (
                  <div className="hub-alert hub-alert-error">
                    <strong>Mapping conflicts detected.</strong> {assistantResult.conflicts.map((item) => item.message).join(" ")} Resolve the duplicate canonical fields above before confirming.
                  </div>
                )}

                <div className="assistant-footer">
                  <label className="hub-field"><span>Mapping name</span><input value={mappingName} onChange={(event) => setMappingName(event.target.value)} /></label>
                  <button className="hub-primary-button" type="button" onClick={confirmAssistantMapping} disabled={busy || Boolean(assistantResult.conflicts?.length)}>
                    {busy ? "Saving..." : "Confirm and save mapping →"}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {activeTab === "register" && (
        <form className="data-panel registration-panel" onSubmit={registerSource}>
          <div className="panel-title">REGISTER AN EXISTING SYSTEM</div>
          <p className="panel-description">
            Register the connection point now. Credentials and secrets are not stored by this form; actual connector synchronization will use the registered source configuration.
          </p>

          <div className="registration-grid">
            <label className="hub-field"><span>Source name</span><input value={registration.name} onChange={(event) => updateRegistration("name", event.target.value)} placeholder="Forward inventory database" required /></label>
            <label className="hub-field"><span>Source type</span><select value={registration.source_type} onChange={(event) => updateRegistration("source_type", event.target.value)}><option value="DATABASE">Database</option><option value="API">Online API</option><option value="DEVICE">Device / Sensor</option><option value="MANUAL">Manual Entry</option></select></label>
            <label className="hub-field"><span>Data category</span><select value={registration.data_category} onChange={(event) => updateRegistration("data_category", event.target.value)}><option value="CUSTOM">Custom</option><option value="INVENTORY">Inventory</option><option value="CONSUMPTION">Daily Consumption</option><option value="VEHICLES">Vehicles</option><option value="SHIPMENTS">Shipments</option><option value="LOCATIONS">Locations</option><option value="ROUTES">Routes</option><option value="WEATHER">Weather</option><option value="DEMAND">Demand</option><option value="MAINTENANCE">Maintenance</option></select></label>
            <label className="hub-field full"><span>Description</span><textarea value={registration.description} onChange={(event) => updateRegistration("description", event.target.value)} placeholder="What information does this source provide?" rows="3" /></label>
          </div>

          {registration.source_type === "DATABASE" && (
            <div className="registration-connection-block">
              <div className="connection-block-title">DATABASE CONNECTION</div>
              <div className="registration-grid">
                <label className="hub-field"><span>Host</span><input value={registration.host} onChange={(event) => updateRegistration("host", event.target.value)} placeholder="database.example.local" /></label>
                <label className="hub-field"><span>Port</span><input value={registration.port} onChange={(event) => updateRegistration("port", event.target.value)} placeholder="5432" /></label>
                <label className="hub-field"><span>Database</span><input value={registration.database} onChange={(event) => updateRegistration("database", event.target.value)} placeholder="logistics" /></label>
                <label className="hub-field"><span>Username</span><input value={registration.username} onChange={(event) => updateRegistration("username", event.target.value)} placeholder="readonly_user" /></label>
              </div>
            </div>
          )}

          {registration.source_type === "API" && (
            <div className="registration-connection-block">
              <div className="connection-block-title">API CONNECTION</div>
              <div className="registration-grid">
                <label className="hub-field full"><span>Endpoint URL</span><input value={registration.api_url} onChange={(event) => updateRegistration("api_url", event.target.value)} placeholder="https://system.example/api/inventory" /></label>
                <label className="hub-field"><span>Method</span><select value={registration.api_method} onChange={(event) => updateRegistration("api_method", event.target.value)}><option>GET</option><option>POST</option></select></label>
              </div>
            </div>
          )}

          {registration.source_type === "DEVICE" && (
            <div className="registration-connection-block">
              <div className="connection-block-title">DEVICE / SENSOR</div>
              <div className="registration-grid">
                <label className="hub-field"><span>Protocol</span><select value={registration.protocol} onChange={(event) => updateRegistration("protocol", event.target.value)}><option>MQTT</option><option>HTTP</option><option>WebSocket</option><option>AMQP</option></select></label>
                <label className="hub-field"><span>Endpoint</span><input value={registration.device_endpoint} onChange={(event) => updateRegistration("device_endpoint", event.target.value)} placeholder="sensor-gateway.local:1883" /></label>
              </div>
            </div>
          )}

          <div className="registration-footer">
            <span>Secrets are intentionally excluded from this registration payload.</span>
            <button className="hub-primary-button" disabled={busy} type="submit">{busy ? "Registering..." : "Register source →"}</button>
          </div>
        </form>
      )}
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
  const [sources, setSources] = useState([]);
  const [sourceHealth, setSourceHealth] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  async function loadObservatory() {
    setLoading(true);
    setError("");

    try {
      const sourcePayload = await fetchJson(
        `${API_URL}/api/management/sources`
      );
      const nextSources = sourcePayload.sources || [];
      setSources(nextSources);

      const health = await Promise.all(
        nextSources.map(async (source) => {
          try {
            const historyPayload = await fetchJson(
              `${API_URL}/api/management/sources/${source.id}/ingestion-history`
            );
            const jobs = historyPayload.jobs || [];
            const latestJob = jobs[0] || null;

            if (!latestJob) {
              return {
                ...source,
                latestJob: null,
                quality: null,
              };
            }

            const qualityPayload = await fetchJson(
              `${API_URL}/api/quality/summary/${latestJob.id}`
            );

            return {
              ...source,
              latestJob,
              quality: qualityPayload.quality || null,
              validation: qualityPayload.validation_errors || null,
            };
          } catch (sourceError) {
            return {
              ...source,
              latestJob: null,
              quality: null,
              sourceError: sourceError.message,
            };
          }
        })
      );

      setSourceHealth(health);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadObservatory();
  }, []);

  const activeCount = sources.filter(
    (source) => source.status === "ACTIVE"
  ).length;

  const averageQuality = useMemo(() => {
    const scores = sourceHealth
      .map((source) => source.quality?.score)
      .filter((score) => Number.isFinite(Number(score)));

    if (!scores.length) {
      return 100;
    }

    return scores.reduce((sum, score) => sum + Number(score), 0) / scores.length;
  }, [sourceHealth]);

  const openErrors = sourceHealth.reduce(
    (sum, source) =>
      sum + Number(source.validation?.open || 0),
    0
  );

  const processedRecords = sourceHealth.reduce(
    (sum, source) =>
      sum + Number(source.quality?.processed_records || 0),
    0
  );

  const quarantinedRecords = sourceHealth.reduce(
    (sum, source) =>
      sum + Number(source.quality?.quarantined_records || 0),
    0
  );

  function qualityClass(score) {
    if (score >= 90) return "quality-good";
    if (score >= 75) return "quality-watch";
    return "quality-risk";
  }

  return (
    <section className="secondary-view observatory-view">
      <div className="view-heading observatory-heading">
        <div>
          <span className="eyebrow">DATA OBSERVATORY</span>
          <h2>Know whether your data can be trusted.</h2>
          <p>
            Monitor source health, freshness, quality and validation activity
            across the common logistics data layer.
          </p>
        </div>

        <button
          className="secondary-button"
          onClick={loadObservatory}
          disabled={loading}
        >
          {loading ? "Refreshing..." : "↻ Refresh observatory"}
        </button>
      </div>

      {error && (
        <div className="data-observatory-error">
          {error}
        </div>
      )}

      <div className="summary-grid observatory-metrics">
        <LargeMetric title="Registered sources" value={sources.length} />
        <LargeMetric title="Active sources" value={activeCount} />
        <LargeMetric
          title="Average quality"
          value={`${averageQuality.toFixed(1)}%`}
        />
        <LargeMetric title="Open errors" value={openErrors} />
      </div>

      <div className="observatory-grid">
        <div className="data-panel observatory-source-panel">
          <div className="panel-heading-row">
            <div>
              <div className="panel-title">SOURCE HEALTH</div>
              <p className="panel-description">
                Every connected source and the quality of its latest ingestion.
              </p>
            </div>
            <span className="observatory-count">
              {sourceHealth.length} sources
            </span>
          </div>

          {loading && !sourceHealth.length ? (
            <div className="observatory-empty">Reading source health...</div>
          ) : sourceHealth.length ? (
            <div className="observatory-table">
              <div className="observatory-row observatory-row-head">
                <span>Source</span>
                <span>Status</span>
                <span>Latest ingestion</span>
                <span>Quality</span>
              </div>

              {sourceHealth.map((source) => {
                const score = source.quality?.score;
                const selectedClass =
                  selected?.id === source.id ? " selected" : "";

                return (
                  <button
                    key={source.id}
                    className={`observatory-row observatory-source-row${selectedClass}`}
                    onClick={() => setSelected(source)}
                  >
                    <span className="observatory-source-name">
                      <strong>{source.name}</strong>
                      <small>
                        {source.source_type} · {source.data_category}
                      </small>
                    </span>

                    <span>
                      <span
                        className={`source-status source-status-${String(
                          source.status
                        ).toLowerCase()}`}
                      >
                        {source.status}
                      </span>
                    </span>

                    <span className="observatory-ingestion-status">
                      <strong>
                        {source.latestJob?.status || "NO INGESTION"}
                      </strong>
                      <small>
                        {source.latestJob?.completed_at
                          ? new Date(
                              source.latestJob.completed_at
                            ).toLocaleString()
                          : "No completed run"}
                      </small>
                    </span>

                    <span className="observatory-quality-cell">
                      <strong className={qualityClass(Number(score ?? 100))}>
                        {score == null ? "—" : `${score}%`}
                      </strong>
                      {source.quality?.grade && (
                        <small>Grade {source.quality.grade}</small>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="observatory-empty">No sources registered.</div>
          )}
        </div>

        <div className="data-panel observatory-detail-panel">
          {selected ? (
            <>
              <div className="panel-title">SOURCE INSPECTION</div>
              <h3>{selected.name}</h3>
              <p className="panel-description">
                {selected.source_type} · {selected.data_category}
              </p>

              <div className="observatory-detail-grid">
                <div>
                  <span>QUALITY</span>
                  <strong>
                    {selected.quality?.score == null
                      ? "No run"
                      : `${selected.quality.score}% · Grade ${selected.quality.grade}`}
                  </strong>
                </div>
                <div>
                  <span>RECORDS</span>
                  <strong>
                    {selected.quality?.total_records ?? 0}
                  </strong>
                </div>
                <div>
                  <span>PROCESSED</span>
                  <strong>
                    {selected.quality?.processed_records ?? 0}
                  </strong>
                </div>
                <div>
                  <span>QUARANTINED</span>
                  <strong>
                    {selected.quality?.quarantined_records ?? 0}
                  </strong>
                </div>
                <div>
                  <span>OPEN ERRORS</span>
                  <strong>
                    {selected.validation?.open ?? 0}
                  </strong>
                </div>
                <div>
                  <span>SCHEMA</span>
                  <strong>
                    {selected.schema_version || "1.0"}
                  </strong>
                </div>
              </div>

              <div className="observatory-insight">
                <span className="eyebrow">OBSERVATION</span>
                <strong>
                  {selected.quality?.grade === "A"
                    ? "This source is currently healthy."
                    : selected.quality?.grade
                      ? "This source needs data-quality attention."
                      : "This source has not completed a quality run yet."}
                </strong>
                <p>
                  {selected.quality
                    ? `${selected.quality.processed_records} records processed and ${selected.quality.quarantined_records} quarantined in the latest ingestion.`
                    : "Run an ingestion and validation cycle to establish a quality baseline."}
                </p>
              </div>
            </>
          ) : (
            <div className="observatory-selection-empty">
              <div className="observatory-empty-icon">◎</div>
              <h3>Select a source</h3>
              <p>
                Inspect quality, ingestion status, record health and validation
                activity for an individual source.
              </p>
            </div>
          )}
        </div>
      </div>

      <div className="observatory-bottom-grid">
        <div className="data-panel">
          <div className="panel-title">DATA QUALITY SIGNALS</div>
          <div className="quality-signal-grid">
            <div>
              <span>PROCESSED RECORDS</span>
              <strong>{processedRecords}</strong>
            </div>
            <div>
              <span>QUARANTINED RECORDS</span>
              <strong>{quarantinedRecords}</strong>
            </div>
            <div>
              <span>OPEN VALIDATION ERRORS</span>
              <strong>{openErrors}</strong>
            </div>
          </div>
        </div>

        <div className="data-panel">
          <div className="panel-title">COMMON DATA LAYER</div>
          <div className="movement-row">
            <strong>GIS operational layer</strong>
            <span>Locations · Vehicles · Shipments</span>
            <span className="healthy-status">CONNECTED</span>
          </div>
          <div className="movement-row">
            <strong>Canonical logistics layer</strong>
            <span>Inventory · Demand · Consumption</span>
            <span className="healthy-status">CONNECTED</span>
          </div>
          <div className="movement-row">
            <strong>AI decision layer</strong>
            <span>Forecast · ETA · Risk · Optimization</span>
            <span className="healthy-status">CONNECTED</span>
          </div>
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
    [
      "logistics",
      "Logistics Management",
    ],
    [
      "optimization",
      "Optimization & What-if",
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