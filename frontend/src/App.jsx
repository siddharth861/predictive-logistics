import { useEffect, useState } from "react";
import { getBackendHealth } from "./services/api";

function App() {
  const [backendStatus, setBackendStatus] = useState("Checking backend...");
  const [error, setError] = useState("");

  useEffect(() => {
    async function checkBackend() {
      try {
        const data = await getBackendHealth();

        if (data.status === "ok") {
          setBackendStatus("Backend connected");
        } else {
          setBackendStatus("Backend responded unexpectedly");
        }
      } catch (err) {
        setBackendStatus("Backend unavailable");
        setError(err.message);
      }
    }

    checkBackend();
  }, []);

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "Arial, sans-serif",
        background: "#f4f5ef",
      }}
    >
      <section
        style={{
          width: "min(600px, 90%)",
          padding: "40px",
          borderRadius: "16px",
          background: "#ffffff",
          boxShadow: "0 10px 30px rgba(0, 0, 0, 0.08)",
          textAlign: "center",
        }}
      >
        <h1>Predictive Logistics</h1>

        <p>
          React frontend is running successfully.
        </p>

        <p>
          Backend status:
          <strong> {backendStatus}</strong>
        </p>

        {error && (
          <p style={{ color: "#b42318" }}>
            {error}
          </p>
        )}
      </section>
    </main>
  );
}

export default App;