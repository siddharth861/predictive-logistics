import { useEffect, useState } from "react";
import App from "./App.jsx";
import Login from "./Login.jsx";
import {
  getCurrentUser,
  getAccessToken,
  logout,
} from "./services/auth.js";
import "./auth.css";

function LoadingScreen() {
  return (
    <div className="auth-loading-screen">
      <div className="auth-loading-card">
        <div className="auth-logo">TL</div>
        <span className="auth-loading-kicker">PREDICTIVE LOGISTICS</span>
        <h1>Securing command environment</h1>
        <div className="auth-loading-line">
          <span />
        </div>
        <p>Verifying operational session...</p>
      </div>
    </div>
  );
}

function AuthenticatedShell({ user, onLogout }) {
  return (
    <div className="authenticated-shell">
      <App />

      <div className="session-chip">
        <div className="session-avatar">
          {user.full_name?.charAt(0)?.toUpperCase() || "U"}
        </div>

        <div className="session-identity">
          <strong>{user.full_name}</strong>
          <span>{user.role.replaceAll("_", " ")}</span>
        </div>

        <button
          className="session-logout"
          type="button"
          onClick={onLogout}
          title="Sign out"
          aria-label="Sign out"
        >
          ↪
        </button>
      </div>
    </div>
  );
}

export default function AuthGate() {
  const [status, setStatus] = useState("checking");
  const [user, setUser] = useState(null);

  async function verifySession() {
    if (!getAccessToken()) {
      setStatus("login");
      return;
    }

    try {
      const currentUser = await getCurrentUser();

      if (!currentUser) {
        setStatus("login");
        return;
      }

      setUser(currentUser);
      setStatus("authenticated");
    } catch (error) {
      console.error("Authentication check failed:", error);
      setStatus("login");
    }
  }

  useEffect(() => {
    verifySession();
  }, []);

  async function handleAuthenticated(authenticatedUser) {
    setUser(authenticatedUser);
    setStatus("authenticated");
  }

  async function handleLogout() {
    await logout();
    setUser(null);
    setStatus("login");
  }

  if (status === "checking") {
    return <LoadingScreen />;
  }

  if (status === "login") {
    return <Login onAuthenticated={handleAuthenticated} />;
  }

  return (
    <AuthenticatedShell
      user={user}
      onLogout={handleLogout}
    />
  );
}
