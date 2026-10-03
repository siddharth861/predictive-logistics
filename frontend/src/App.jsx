import { useEffect, useMemo, useState } from "react";
import { getBackendHealth } from "./services/api";
import "./App.css";

const API_URL = "http://localhost:8001";

const navigation = [
  { id: "command", label: "Command Centre", icon: "⌂" },
  { id: "operations", label: "Operations", icon: "◈" },
  { id: "map", label: "Operational Map", icon: "◎" },
  { id: "ai", label: "AI Intelligence", icon: "✦" },
  { id: "optimization", label: "Optimization", icon: "⇄" },
  { id: "data", label: "Data Hub", icon: "▦" },
];

async function fetchJson(endpoint) {
  const response = await fetch(`${API_URL}${endpoint}`);

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

function App() {
  const [activePage, setActivePage] = useState("command");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [systemStatus, setSystemStatus] = useState("Checking");
  const [inventory, setInventory] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [shipments, setShipments] = useState([]);

  const [loadingKpis, setLoadingKpis] = useState(true);
  const [dataError, setDataError] = useState("");

  useEffect(() => {
    let mounted = true;

    async function loadDashboardData() {
      setLoadingKpis(true);
      setDataError("");

      try {
        const [health, inventoryResponse, vehicleResponse, shipmentResponse] =
          await Promise.all([
            getBackendHealth(),
            fetchJson("/api/logistics/inventory"),
            fetchJson("/api/logistics/vehicles"),
            fetchJson("/api/logistics/shipments"),
          ]);

        if (!mounted) {
          return;
        }

        if (health?.status === "healthy" || health?.status === "ok") {
          setSystemStatus("Operational");
        } else {
          setSystemStatus("Degraded");
        }

        setInventory(inventoryResponse?.inventory ?? []);
        setVehicles(vehicleResponse?.vehicles ?? []);
        setShipments(shipmentResponse?.shipments ?? []);
      } catch (error) {
        if (!mounted) {
          return;
        }

        setSystemStatus("Offline");
        setDataError(error.message || "Unable to load dashboard data.");
      } finally {
        if (mounted) {
          setLoadingKpis(false);
        }
      }
    }

    loadDashboardData();

    return () => {
      mounted = false;
    };
  }, []);

  const dashboardMetrics = useMemo(() => {
    const totalInventory = inventory.reduce(
      (sum, record) => sum + Number(record.quantity || 0),
      0,
    );

    const totalMaximumStock = inventory.reduce(
      (sum, record) => sum + Number(record.maximum_stock || 0),
      0,
    );

    const inventoryUtilization =
      totalMaximumStock > 0
        ? (totalInventory / totalMaximumStock) * 100
        : 0;

    const availableVehicles = vehicles.filter(
      (vehicle) =>
        String(vehicle.status || "").toUpperCase() === "AVAILABLE" &&
        vehicle.is_active !== false,
    ).length;

    const activeVehicles = vehicles.filter(
      (vehicle) => vehicle.is_active !== false,
    ).length;

    const activeShipments = shipments.filter((shipment) =>
      ["PLANNED", "DISPATCHED", "IN_TRANSIT"].includes(
        String(shipment.status || "").toUpperCase(),
      ),
    ).length;

    const deliveredShipments = shipments.filter(
      (shipment) =>
        String(shipment.status || "").toUpperCase() === "DELIVERED",
    ).length;

    const delayedShipments = shipments.filter((shipment) => {
      const status = String(shipment.status || "").toUpperCase();

      if (status === "DELIVERED") {
        if (!shipment.estimated_arrival || !shipment.actual_arrival) {
          return false;
        }

        return (
          new Date(shipment.actual_arrival).getTime() >
          new Date(shipment.estimated_arrival).getTime()
        );
      }

      return false;
    }).length;

    return {
      totalInventory,
      inventoryUtilization,
      totalVehicles: vehicles.length,
      availableVehicles,
      activeVehicles,
      activeShipments,
      deliveredShipments,
      delayedShipments,
      totalShipments: shipments.length,
    };
  }, [inventory, vehicles, shipments]);

  const formatNumber = (value, decimals = 0) =>
    Number(value || 0).toLocaleString("en-IN", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });

  const kpis = [
    {
      label: "Inventory",
      value: loadingKpis
        ? "..."
        : `${formatNumber(dashboardMetrics.totalInventory, 1)} L`,
      detail: loadingKpis
        ? "Loading..."
        : `${formatNumber(dashboardMetrics.inventoryUtilization, 0)}% capacity`,
      tone: "olive",
    },
    {
      label: "Active Shipments",
      value: loadingKpis
        ? "..."
        : formatNumber(dashboardMetrics.activeShipments),
      detail: loadingKpis
        ? "Loading..."
        : `${formatNumber(dashboardMetrics.totalShipments)} total`,
      tone: "amber",
    },
    {
      label: "Available Vehicles",
      value: loadingKpis
        ? "..."
        : `${formatNumber(dashboardMetrics.availableVehicles)}/${formatNumber(
            dashboardMetrics.totalVehicles,
          )}`,
      detail: loadingKpis
        ? "Loading..."
        : `${formatNumber(
            dashboardMetrics.activeVehicles,
          )} active fleet assets`,
      tone: "blue",
    },
    {
      label: "Delivered",
      value: loadingKpis
        ? "..."
        : formatNumber(dashboardMetrics.deliveredShipments),
      detail: loadingKpis
        ? "Loading..."
        : `${formatNumber(
            dashboardMetrics.delayedShipments,
          )} delayed on arrival`,
      tone: "green",
    },
  ];

  const pageContent = {
    operations: {
      title: "Operations",
      subtitle: "Operational logistics monitoring and workflow control.",
    },
    map: {
      title: "Operational Map",
      subtitle: "GIS-based logistics picture and movement context.",
    },
    ai: {
      title: "AI Intelligence",
      subtitle: "Forecasts, risk signals, anomalies and explainable insights.",
    },
    optimization: {
      title: "Optimization",
      subtitle: "Resource allocation and route-aware planning.",
    },
    data: {
      title: "Data Hub",
      subtitle: "Connected sources, ingestion health and canonical data.",
    },
  };

  function renderPlaceholderPage(page) {
    const content = pageContent[page];

    return (
      <section className="module-page">
        <div className="module-page-icon">{navigation.find((item) => item.id === page)?.icon}</div>
        <h2>{content.title}</h2>
        <p>{content.subtitle}</p>
        <div className="module-page-note">
          This module will be connected to the completed backend services in the
          next frontend stages.
        </div>
      </section>
    );
  }

  return (
    <div className="app-shell">
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand-block">
          <div className="brand-mark">PL</div>
          <div>
            <div className="brand-title">PREDICTIVE</div>
            <div className="brand-subtitle">LOGISTICS PLATFORM</div>
          </div>
        </div>

        <div className="sidebar-section-label">COMMAND</div>

        <nav className="main-navigation">
          {navigation.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`nav-item ${
                activePage === item.id ? "nav-item-active" : ""
              }`}
              onClick={() => {
                setActivePage(item.id);
                setSidebarOpen(false);
              }}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="system-status-card">
            <div className="status-heading">
              <span
                className={`status-dot ${
                  systemStatus === "Operational"
                    ? "status-online"
                    : systemStatus === "Checking"
                      ? "status-checking"
                      : "status-offline"
                }`}
              />
              <span>System Status</span>
            </div>

            <strong>{systemStatus}</strong>

            <span className="status-description">
              {systemStatus === "Operational"
                ? "All connected services responding"
                : systemStatus === "Checking"
                  ? "Checking backend services"
                  : "Backend connection unavailable"}
            </span>
          </div>

          <div className="sidebar-footer">
            <span>SIH 2026</span>
            <span>•</span>
            <span>DEMO ENVIRONMENT</span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <button
            className="mobile-menu-button"
            type="button"
            aria-label="Open navigation"
            onClick={() => setSidebarOpen(true)}
          >
            ☰
          </button>

          <div className="topbar-heading">
            <span className="eyebrow">OPERATIONS / LIVE PICTURE</span>
            <h1>
              {activePage === "command"
                ? "Command Centre"
                : pageContent[activePage]?.title}
            </h1>
          </div>

          <div className="topbar-actions">
            <div className="environment-pill">
              <span className="environment-dot" />
              SYNTHETIC DATA
            </div>

            <div className="user-badge">LO</div>
          </div>
        </header>

        {activePage === "command" ? (
          <div className="dashboard-content">
            <section className="welcome-strip">
              <div>
                <span className="section-kicker">OPERATIONAL OVERVIEW</span>
                <h2>Logistics Command Picture</h2>
                <p>
                  Monitor supply readiness, fleet availability and movement
                  activity from the unified logistics data layer.
                </p>
              </div>

              <div className="refresh-indicator">
                <span className="pulse-dot" />
                LIVE DATA
              </div>
            </section>

            {dataError && (
              <div className="data-warning">
                <strong>Dashboard data warning</strong>
                <span>{dataError}</span>
              </div>
            )}

            <section className="kpi-grid">
              {kpis.map((kpi) => (
                <article className={`kpi-card kpi-${kpi.tone}`} key={kpi.label}>
                  <div className="kpi-topline">
                    <span>{kpi.label}</span>
                    <span className="kpi-indicator" />
                  </div>

                  <strong>{kpi.value}</strong>
                  <span>{kpi.detail}</span>
                </article>
              ))}
            </section>

            <section className="dashboard-grid">
              <article className="panel map-panel">
                <div className="panel-header">
                  <div>
                    <span className="panel-kicker">GEOSPATIAL</span>
                    <h3>Operational Map</h3>
                  </div>

                  <button type="button" className="panel-action">
                    OPEN MAP
                  </button>
                </div>

                <div className="map-placeholder">
                  <div className="map-grid-lines" />

                  <div className="map-route map-route-one" />
                  <div className="map-route map-route-two" />

                  <div className="map-node map-node-depot">
                    <span />
                    <label>DEPOT-A</label>
                  </div>

                  <div className="map-node map-node-forward">
                    <span />
                    <label>FORWARD-B</label>
                  </div>

                  <div className="map-coordinate coordinate-one">
                    19.0760° N / 72.8777° E
                  </div>

                  <div className="map-coordinate coordinate-two">
                    19.2183° N / 72.9781° E
                  </div>

                  <div className="map-overlay-label">
                    <span>ROUTE STATUS</span>
                    <strong>NOMINAL</strong>
                  </div>
                </div>
              </article>

              <article className="panel brief-panel">
                <div className="panel-header">
                  <div>
                    <span className="panel-kicker">DECISION INTELLIGENCE</span>
                    <h3>AI Logistics Brief</h3>
                  </div>

                  <span className="confidence-badge">90.9% CONF.</span>
                </div>

                <div className="brief-main">
                  <div className="brief-icon">✦</div>

                  <div>
                    <span className="brief-label">FORECAST SIGNAL</span>
                    <h4>Fuel demand remains within expected range.</h4>
                    <p>
                      Current inventory remains above the configured minimum
                      stock threshold for the active demonstration dataset.
                    </p>
                  </div>
                </div>

                <div className="brief-metrics">
                  <div>
                    <span>Forecast</span>
                    <strong>39.4 L</strong>
                  </div>
                  <div>
                    <span>Stock Cover</span>
                    <strong>12.7 days</strong>
                  </div>
                  <div>
                    <span>Risk</span>
                    <strong className="text-low">LOW</strong>
                  </div>
                </div>

                <button
                  type="button"
                  className="full-width-button"
                  onClick={() => setActivePage("ai")}
                >
                  VIEW AI INTELLIGENCE
                </button>
              </article>
            </section>

            <section className="bottom-grid">
              <article className="panel alerts-panel">
                <div className="panel-header">
                  <div>
                    <span className="panel-kicker">ATTENTION</span>
                    <h3>Operational Alerts</h3>
                  </div>

                  <span className="alert-count">0 ACTIVE</span>
                </div>

                <div className="empty-alerts">
                  <div className="empty-alert-icon">✓</div>
                  <div>
                    <strong>No active critical alerts</strong>
                    <span>
                      The current synthetic operational dataset has no unresolved
                      critical logistics alerts.
                    </span>
                  </div>
                </div>
              </article>

              <article className="panel supply-panel">
                <div className="panel-header">
                  <div>
                    <span className="panel-kicker">MOVEMENT</span>
                    <h3>Supply Flow</h3>
                  </div>

                  <button
                    type="button"
                    className="panel-action"
                    onClick={() => setActivePage("operations")}
                  >
                    DETAILS
                  </button>
                </div>

                <div className="flow-row">
                  <div className="flow-location">
                    <span className="flow-node flow-node-source" />
                    <div>
                      <strong>DEPOT-A</strong>
                      <span>Source</span>
                    </div>
                  </div>

                  <div className="flow-line">
                    <span />
                  </div>

                  <div className="flow-vehicle">TRK-001</div>

                  <div className="flow-line">
                    <span />
                  </div>

                  <div className="flow-location">
                    <span className="flow-node flow-node-destination" />
                    <div>
                      <strong>FORWARD-B</strong>
                      <span>Destination</span>
                    </div>
                  </div>
                </div>

                <div className="flow-footer">
                  <span>Last movement</span>
                  <strong>100 L FUEL • DELIVERED</strong>
                </div>
              </article>
            </section>
          </div>
        ) : (
          <div className="dashboard-content">
            {renderPlaceholderPage(activePage)}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;