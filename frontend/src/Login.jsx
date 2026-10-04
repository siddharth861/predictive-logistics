import { useState } from "react";
import {
  getCurrentUser,
  login,
  register,
} from "./services/auth.js";

export default function Login({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setBusy(true);

    try {
      if (mode === "register") {
        await register({
          email: email.trim(),
          full_name: fullName.trim(),
          password,
        });

        setMode("login");
        setPassword("");
        setMessage("Account created. Sign in to enter the command centre.");
        return;
      }

      await login(email.trim(), password);
      const user = await getCurrentUser();

      if (!user) {
        throw new Error("Login succeeded but the user session could not be loaded.");
      }

      await onAuthenticated(user);
    } catch (submitError) {
      setError(submitError.message || "Unable to complete the request.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-screen">
      <div className="login-grid-decoration" />

      <section className="login-panel login-panel-brand">
        <div className="login-brand-row">
          <div className="login-logo">TL</div>
          <div>
            <span className="login-kicker">PREDICTIVE LOGISTICS</span>
            <strong>Trust Logistics</strong>
          </div>
        </div>

        <div className="login-hero-copy">
          <span className="login-eyebrow">DECISION INTELLIGENCE PLATFORM</span>
          <h1>Turn fragmented logistics data into a clear operational picture.</h1>
          <p>
            Unified data, GIS intelligence, predictive risk and optimization in one
            command environment.
          </p>
        </div>

        <div className="login-capabilities">
          <div>
            <span>01</span>
            <strong>Universal Data</strong>
            <p>Connect files, systems and operational sources.</p>
          </div>
          <div>
            <span>02</span>
            <strong>Predictive Intelligence</strong>
            <p>Forecast demand, risk and movement outcomes.</p>
          </div>
          <div>
            <span>03</span>
            <strong>Decision Support</strong>
            <p>Compare scenarios and select feasible plans.</p>
          </div>
        </div>

        <div className="login-footer-note">
          Synthetic demonstration environment · No operational military data
        </div>
      </section>

      <section className="login-panel login-panel-form">
        <div className="login-form-wrap">
          <span className="login-eyebrow">
            {mode === "login" ? "SECURE ACCESS" : "NEW OPERATOR"}
          </span>

          <h2>
            {mode === "login"
              ? "Enter the command centre"
              : "Create an operator account"}
          </h2>

          <p className="login-subtitle">
            {mode === "login"
              ? "Authenticate to access the logistics workspace."
              : "New accounts are created with the ANALYST role by default."}
          </p>

          {error && <div className="login-alert login-alert-error">{error}</div>}
          {message && <div className="login-alert login-alert-success">{message}</div>}

          <form onSubmit={handleSubmit}>
            {mode === "register" && (
              <label>
                <span>Full name</span>
                <input
                  type="text"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Operator name"
                  autoComplete="name"
                  required
                />
              </label>
            )}

            <label>
              <span>Email</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="operator@example.com"
                autoComplete="email"
                required
              />
            </label>

            <label>
              <span>Password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={8}
                required
              />
            </label>

            <button
              className="login-submit"
              type="submit"
              disabled={busy}
            >
              {busy
                ? mode === "login"
                  ? "Authenticating..."
                  : "Creating account..."
                : mode === "login"
                  ? "Enter command centre"
                  : "Create account"}
              <span>→</span>
            </button>
          </form>

          <button
            className="login-mode-toggle"
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError("");
              setMessage("");
            }}
          >
            {mode === "login"
              ? "Need a new account? Register"
              : "Already have an account? Sign in"}
          </button>
        </div>

        <div className="login-security-note">
          <span className="security-dot" />
          JWT authenticated session · Role-based access enabled
        </div>
      </section>
    </main>
  );
}
