import { useEffect, useState } from "react";
import { getBackendHealth } from "./services/api";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8001";

const CANONICAL_FIELDS = [
  "ITEM_CODE",
  "ITEM_NAME",
  "QUANTITY",
  "LOCATION",
  "DATE",
  "CONSUMPTION",
  "VEHICLE_ID",
  "SHIPMENT_ID",
  "ROUTE_ID",
  "DEMAND",
];

function App() {
  const [backendStatus, setBackendStatus] = useState("Checking backend...");
  const [error, setError] = useState("");

  const [sourceId, setSourceId] = useState("");
  const [sources, setSources] = useState([]);

  const [assistantData, setAssistantData] = useState(null);
  const [mappings, setMappings] = useState({});
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    checkBackend();
    loadSources();
  }, []);

  async function checkBackend() {
    try {
      const data = await getBackendHealth();

      if (data.status === "ok") {
        setBackendStatus("Connected");
      } else {
        setBackendStatus("Unexpected response");
      }
    } catch (err) {
      setBackendStatus("Unavailable");
      setError(err.message);
    }
  }

  async function loadSources() {
    try {
      const response = await fetch(`${API_URL}/api/management/sources`);

      if (!response.ok) {
        throw new Error("Could not load data sources.");
      }

      const data = await response.json();

      /*
       * Remove duplicate source IDs before displaying them.
       */
      const uniqueSources = Array.from(
        new Map(
          (data.sources || []).map((source) => [source.id, source])
        ).values()
      );

      setSources(uniqueSources);
    } catch (err) {
      setError(err.message);
    }
  }

  async function analyzeSource() {
    if (!sourceId) {
      setError("Please select a data source first.");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");
    setAssistantData(null);
    setMappings({});

    try {
      const response = await fetch(
        `${API_URL}/api/ingestion/assistant?source_id=${sourceId}`,
        {
          method: "POST",
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Data Assistant failed.");
      }

      setAssistantData(data);

      /*
       * Build the editable mapping from the assistant's
       * actual detected field.
       */
      const initialMappings = {};

      (data.suggestions || []).forEach((item) => {
        const sourceColumn =
          item.source_column ||
          item.source_field ||
          item.column ||
          item.field;

        const suggestedField =
          item.suggested_field ||
          item.canonical_field ||
          item.suggested_canonical_field ||
          "";

        if (sourceColumn) {
          initialMappings[sourceColumn] = suggestedField;
        }
      });

      setMappings(initialMappings);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function updateMapping(sourceColumn, value) {
    setMappings((previous) => ({
      ...previous,
      [sourceColumn]: value,
    }));
  }

  async function confirmMapping() {
    if (!assistantData) {
      return;
    }

    setConfirming(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch(
        `${API_URL}/api/ingestion/confirm-mapping`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            source_id: assistantData.source_id,
            overrides: mappings,
            name: "Data Assistant confirmed mapping",
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Mapping confirmation failed.");
      }

      setMessage(
        `Mapping confirmed successfully. Version ${data.version} is now active.`
      );

      setAssistantData((previous) => ({
        ...previous,
        mapping_config_id: data.mapping_config_id,
        version: data.version,
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setConfirming(false);
    }
  }

  const summary = assistantData?.summary;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">PREDICTIVE LOGISTICS</div>

          <h1>Data Assistant</h1>

          <p>
            Connect logistics data and let the system understand its structure.
          </p>
        </div>

        <div
          className={`connection-status ${
            backendStatus === "Connected" ? "online" : "offline"
          }`}
        >
          <span className="status-dot"></span>
          {backendStatus}
        </div>
      </header>

      <section className="assistant-card">
        <div className="section-heading">
          <div>
            <span className="section-number">01</span>

            <div>
              <h2>Select Data Source</h2>

              <p>
                Choose an uploaded source that the Data Assistant should
                analyze.
              </p>
            </div>
          </div>
        </div>

        <div className="source-row">
          <select
            value={sourceId}
            onChange={(event) => {
              setSourceId(event.target.value);
              setAssistantData(null);
              setMappings({});
              setMessage("");
              setError("");
            }}
          >
            <option value="">Select a data source...</option>

            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.name} — {source.data_category || "CUSTOM"}
              </option>
            ))}
          </select>

          <button
            className="primary-button"
            onClick={analyzeSource}
            disabled={loading || !sourceId}
          >
            {loading ? "Analyzing..." : "Analyze Data"}
          </button>
        </div>
      </section>

      {error && (
        <div className="alert error">
          <strong>Error</strong>
          <span>{error}</span>
        </div>
      )}

      {message && (
        <div className="alert success">
          <strong>Success</strong>
          <span>{message}</span>
        </div>
      )}

      {assistantData && (
        <>
          <section className="assistant-card">
            <div className="section-heading">
              <div>
                <span className="section-number">02</span>

                <div>
                  <h2>Data Understanding</h2>

                  <p>
                    The assistant inspected the source and generated mapping
                    suggestions.
                  </p>
                </div>
              </div>
            </div>

            <div className="stats-grid">
              <div className="stat-card">
                <span>Columns</span>
                <strong>{summary?.total_columns || 0}</strong>
              </div>

              <div className="stat-card">
                <span>Auto Mapped</span>
                <strong>{summary?.auto_mapped || 0}</strong>
              </div>

              <div className="stat-card">
                <span>Suggestions</span>
                <strong>{summary?.suggestions || 0}</strong>
              </div>

              <div className="stat-card">
                <span>Needs Review</span>
                <strong>{summary?.needs_review || 0}</strong>
              </div>

              <div className="stat-card">
                <span>Conflicts</span>
                <strong>{summary?.conflicts || 0}</strong>
              </div>
            </div>
          </section>

          <section className="assistant-card">
            <div className="section-heading">
              <div>
                <span className="section-number">03</span>

                <div>
                  <h2>Review Mapping</h2>

                  <p>
                    Review the assistant's decisions before saving the mapping.
                  </p>
                </div>
              </div>
            </div>

            <div className="mapping-table">
              <div className="mapping-header">
                <span>Source Field</span>
                <span>AI Decision</span>
                <span>Confidence</span>
                <span>Canonical Field</span>
              </div>

              {(assistantData.suggestions || []).map((item, index) => {
                const sourceColumn =
                  item.source_column ||
                  item.source_field ||
                  item.column ||
                  item.field ||
                  `Field ${index + 1}`;

                const confidence = Math.round(
                  (item.confidence || 0) * 100
                );

                return (
                  <div className="mapping-row" key={sourceColumn}>
                    <div>
                      <strong>{sourceColumn}</strong>
                    </div>

                    <div>
                      <span
                        className={`decision ${
                          item.decision === "AUTO"
                            ? "auto"
                            : item.decision === "SUGGEST"
                            ? "suggest"
                            : "review"
                        }`}
                      >
                        {item.decision || "REVIEW"}
                      </span>
                    </div>

                    <div>
                      <div className="confidence-wrapper">
                        <div className="confidence-bar">
                          <div
                            className="confidence-fill"
                            style={{
                              width: `${confidence}%`,
                            }}
                          ></div>
                        </div>

                        <span>{confidence}%</span>
                      </div>
                    </div>

                    <div>
                      <select
                        value={mappings[sourceColumn] || ""}
                        onChange={(event) =>
                          updateMapping(
                            sourceColumn,
                            event.target.value
                          )
                        }
                      >
                        <option value="">Do not map</option>

                        {CANONICAL_FIELDS.map((field) => (
                          <option key={field} value={field}>
                            {field}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="confirmation-area">
              <div>
                <strong>Ready to save?</strong>

                <p>
                  The confirmed mapping will become the active version for
                  this source.
                </p>
              </div>

              <button
                className="primary-button"
                onClick={confirmMapping}
                disabled={confirming}
              >
                {confirming ? "Saving..." : "Confirm Mapping"}
              </button>
            </div>
          </section>

          {assistantData.version && (
            <section className="version-card">
              <div className="version-icon">✓</div>

              <div>
                <strong>Active Mapping Version</strong>

                <p>
                  Version {assistantData.version} is active for this data
                  source.
                </p>
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}

export default App;