import { useEffect, useState } from "react";
import { getBackendHealth } from "./services/api";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8001";

const NAV_ITEMS = [
  { id: "overview", label: "Command Centre", icon: "⌂" },
  { id: "operations", label: "Operations", icon: "◈" },
  { id: "map", label: "Operational Map", icon: "◎" },
  { id: "ai", label: "AI Intelligence", icon: "✦" },
  { id: "optimization", label: "Optimization", icon: "⇄" },
  { id: "data", label: "Data Hub", icon: "▦" },
];

function App() {
  const [activeView, setActiveView] = useState("overview");
  const [backendStatus, setBackendStatus] = useState("Checking");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    checkBackend();
  }, []);

  async function checkBackend() {
    try {
      const data = await getBackendHealth();

      if (data.status === "healthy" || data.status === "ok") {
        setBackendStatus("Operational");
      } else {
        setBackendStatus("Unexpected");
      }
    } catch {
      setBackendStatus("Offline");
    }
  }

  function handleNavigation(view) {
    setActiveView(view);
    setSidebarOpen(false);
  }

  const activeItem =
    NAV_ITEMS.find((item) => item.id === activeView) || NAV_ITEMS[0];

  return (
    <div className="command-shell">
      {sidebarOpen && (
        <button
          className="mobile-overlay"
          onClick={() => setSidebarOpen(false)}
          aria-label="Close navigation"
        />
      )}

      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">
            <span className="brand-mark-inner">PL</span>
          </div>

          <div>
            <div className="brand-name">PREDICTIVE</div>
            <div className="brand-subtitle">LOGISTICS COMMAND</div>
          </div>
        </div>

        <div className="sidebar-divider" />

        <div className="nav-label">COMMAND MODULES</div>

        <nav className="navigation">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${
                activeView === item.id ? "active" : ""
              }`}
              onClick={() => handleNavigation(item.id)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>

              {activeView === item.id && <span className="active-indicator" />}
            </button>
          ))}
        </nav>

        <div className="sidebar-spacer" />

        <div className="system-card">
          <div className="system-card-header">
            <span className="system-pulse" />
            SYSTEM STATUS
          </div>

          <strong>{backendStatus}</strong>

          <p>
            Core logistics services are being monitored through the command
            centre.
          </p>
        </div>

        <div className="sidebar-footer">
          <span>PLATFORM</span>
          <strong>v0.1 • SIH 2026</strong>
        </div>
      </aside>

      <main className="main-area">
        <header className="command-header">
          <div className="header-left">
            <button
              className="mobile-menu"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation"
            >
              ☰
            </button>

            <div>
              <div className="breadcrumb">
                COMMAND CENTRE <span>/</span> {activeItem.label.toUpperCase()}
              </div>

              <h1>{activeItem.label}</h1>
            </div>
          </div>

          <div className="header-right">
            <div className="header-clock">
              <span className="clock-dot" />
              LIVE OPERATIONAL VIEW
            </div>

            <div className="header-user">
              <div className="user-avatar">LO</div>
              <div className="user-info">
                <strong>Logistics Officer</strong>
                <span>Command Access</span>
              </div>
            </div>
          </div>
        </header>

        {activeView === "overview" && (
          <CommandOverview backendStatus={backendStatus} />
        )}

        {activeView !== "overview" && (
          <ModulePlaceholder
            title={activeItem.label}
            description={getModuleDescription(activeView)}
            icon={activeItem.icon}
          />
        )}
      </main>
    </div>
  );
}

function CommandOverview({ backendStatus }) {
  return (
    <div className="dashboard">
      <section className="hero-strip">
        <div>
          <div className="eyebrow">
            LOGISTICS OPERATIONS • SYNTHETIC DEMONSTRATION DATA
          </div>

          <h2>Operational Picture</h2>

          <p>
            A unified view of supply readiness, movement, demand and
            decision-support intelligence.
          </p>
        </div>

        <div className="hero-status">
          <div className="hero-status-label">SYSTEM</div>
          <strong>{backendStatus}</strong>
          <span>All command services</span>
        </div>
      </section>

      <section className="kpi-grid">
        <KpiCard
          label="SUPPLY READINESS"
          value="92%"
          detail="Across monitored locations"
          status="stable"
        />

        <KpiCard
          label="ACTIVE SHIPMENTS"
          value="31"
          detail="Currently tracked"
          status="stable"
        />

        <KpiCard
          label="LOW STOCK EVENTS"
          value="01"
          detail="Requires attention"
          status="warning"
        />

        <KpiCard
          label="AI FORECAST"
          value="39.4"
          unit="L"
          detail="Next-day fuel demand"
          status="ai"
        />
      </section>

      <section className="workspace-grid">
        <div className="panel map-panel">
          <PanelHeader
            eyebrow="01 • SITUATIONAL AWARENESS"
            title="Operational Map"
            action="OPEN MAP"
          />

          <div className="map-placeholder">
            <div className="map-grid" />

            <div className="map-coordinate top-left">19°04'33"N</div>
            <div className="map-coordinate top-right">72°52'39"E</div>

            <div className="map-route route-one" />
            <div className="map-route route-two" />

            <MapNode
              className="node-depot"
              label="DEPOT-A"
              type="DEPOT"
            />

            <MapNode
              className="node-forward"
              label="FORWARD-B"
              type="FORWARD"
            />

            <div className="map-center-label">
              <span>OPERATIONAL AREA</span>
              <strong>LIVE LOGISTICS NETWORK</strong>
            </div>

            <div className="map-legend">
              <div>
                <span className="legend-dot depot" />
                Depot
              </div>

              <div>
                <span className="legend-dot forward" />
                Forward Location
              </div>

              <div>
                <span className="legend-line" />
                Supply Route
              </div>
            </div>
          </div>
        </div>

        <div className="right-stack">
          <div className="panel intelligence-panel">
            <PanelHeader
              eyebrow="02 • DECISION INTELLIGENCE"
              title="AI Logistics Brief"
              action="VIEW"
            />

            <div className="ai-summary">
              <div className="ai-symbol">✦</div>

              <div>
                <strong>Fuel demand is expected to remain stable.</strong>

                <p>
                  Forecast indicates approximately 39.4 L/day for the next
                  planning period.
                </p>
              </div>
            </div>

            <div className="ai-metrics">
              <div>
                <span>CONFIDENCE</span>
                <strong>90.95%</strong>
              </div>

              <div>
                <span>RISK</span>
                <strong className="low-risk">LOW</strong>
              </div>

              <div>
                <span>COVER</span>
                <strong>12.7d</strong>
              </div>
            </div>
          </div>

          <div className="panel alerts-panel">
            <PanelHeader
              eyebrow="03 • ATTENTION"
              title="Operational Alerts"
              action="ALL"
            />

            <AlertRow
              severity="warning"
              title="Low stock threshold"
              description="DEPOT-A • Fuel inventory requires monitoring"
              time="ACTIVE"
            />

            <AlertRow
              severity="info"
              title="Route monitoring"
              description="31 shipment records available for analysis"
              time="LIVE"
            />

            <AlertRow
              severity="success"
              title="System healthy"
              description="Core backend services responding normally"
              time="NOW"
            />
          </div>
        </div>
      </section>

      <section className="bottom-grid">
        <div className="panel supply-panel">
          <PanelHeader
            eyebrow="04 • SUPPLY NETWORK"
            title="Supply Flow"
            action="EXPLORE"
          />

          <div className="supply-flow">
            <div className="flow-location">
              <span className="flow-node depot-node" />

              <div>
                <strong>DEPOT-A</strong>
                <span>Primary Supply Node</span>
              </div>
            </div>

            <div className="flow-connector">
              <span>18.97 km</span>

              <div className="connector-line">
                <i />
                <i />
                <i />
              </div>
            </div>

            <div className="flow-location">
              <span className="flow-node forward-node" />

              <div>
                <strong>FORWARD-B</strong>
                <span>Destination Node</span>
              </div>
            </div>
          </div>
        </div>

        <div className="panel optimization-panel">
          <PanelHeader
            eyebrow="05 • PLANNING"
            title="Optimization"
            action="OPEN"
          />

          <div className="optimization-result">
            <div>
              <span>RECOMMENDED RESUPPLY</span>

              <strong>
                54.6 <small>L</small>
              </strong>
            </div>

            <div className="optimization-status">
              <span className="status-check">✓</span>

              <div>
                <strong>FEASIBLE</strong>
                <span>Vehicle and route constraints satisfied</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <footer className="dashboard-footer">
        <span>Predictive Logistics Command Centre</span>
        <span>Prototype • Synthetic / Non-sensitive Data</span>
      </footer>
    </div>
  );
}

function KpiCard({ label, value, unit, detail, status }) {
  return (
    <div className={`kpi-card ${status}`}>
      <div className="kpi-top">
        <span>{label}</span>
        <i />
      </div>

      <div className="kpi-value">
        {value}
        {unit && <small>{unit}</small>}
      </div>

      <div className="kpi-detail">{detail}</div>
    </div>
  );
}

function PanelHeader({ eyebrow, title, action }) {
  return (
    <div className="panel-header">
      <div>
        <span>{eyebrow}</span>
        <h3>{title}</h3>
      </div>

      <button>{action} ↗</button>
    </div>
  );
}

function MapNode({ className, label, type }) {
  return (
    <div className={`map-node ${className}`}>
      <div className="map-node-marker">
        <span />
      </div>

      <div className="map-node-label">
        <strong>{label}</strong>
        <span>{type}</span>
      </div>
    </div>
  );
}

function AlertRow({ severity, title, description, time }) {
  return (
    <div className="alert-row">
      <span className={`alert-marker ${severity}`} />

      <div className="alert-content">
        <strong>{title}</strong>
        <span>{description}</span>
      </div>

      <small>{time}</small>
    </div>
  );
}

function ModulePlaceholder({ title, description, icon }) {
  return (
    <div className="module-page">
      <div className="module-placeholder">
        <div className="module-icon">{icon}</div>

        <div className="eyebrow">COMMAND MODULE</div>

        <h2>{title}</h2>

        <p>{description}</p>

        <div className="module-progress">
          <span>MODULE FOUNDATION</span>
          <strong>READY FOR INTEGRATION</strong>
        </div>
      </div>
    </div>
  );
}

function getModuleDescription(view) {
  const descriptions = {
    operations:
      "Monitor inventory, shipments, vehicles and logistics events from one operational workspace.",
    map:
      "Explore locations, routes, movement and geographic logistics intelligence.",
    ai:
      "Review demand forecasts, risk signals, anomalies and explainable AI insights.",
    optimization:
      "Generate feasible supply plans and compare operational what-if scenarios.",
    data:
      "Manage connected sources, ingestion health, data quality, mappings and lineage.",
  };

  return descriptions[view] || "Command module ready for integration.";
}

export default App;