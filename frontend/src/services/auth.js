const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8001";

const ACCESS_TOKEN_KEY = "predictive_logistics_access_token";
const REFRESH_TOKEN_KEY = "predictive_logistics_refresh_token";

function readStorage(key) {
  return localStorage.getItem(key);
}

export function getAccessToken() {
  return readStorage(ACCESS_TOKEN_KEY);
}

export function getRefreshToken() {
  return readStorage(REFRESH_TOKEN_KEY);
}

export function saveTokens(tokens) {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    return response.json();
  }

  return response.text();
}

function getErrorMessage(payload, fallback) {
  if (typeof payload === "string" && payload.trim()) {
    return payload;
  }

  if (payload?.detail) {
    return Array.isArray(payload.detail)
      ? payload.detail.map((item) => item.msg).join(", ")
      : payload.detail;
  }

  return fallback;
}

export async function login(email, password) {
  const response = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, password }),
  });

  const payload = await parseResponse(response);

  if (!response.ok) {
    throw new Error(
      getErrorMessage(payload, `Login failed: ${response.status}`)
    );
  }

  saveTokens(payload);
  return payload;
}

export async function register({ email, full_name, password }) {
  const response = await fetch(`${API_URL}/api/auth/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, full_name, password }),
  });

  const payload = await parseResponse(response);

  if (!response.ok) {
    throw new Error(
      getErrorMessage(payload, `Registration failed: ${response.status}`)
    );
  }

  return payload;
}

export async function refreshSession() {
  const refreshToken = getRefreshToken();

  if (!refreshToken) {
    return false;
  }

  try {
    const response = await fetch(`${API_URL}/api/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    const payload = await parseResponse(response);

    if (!response.ok) {
      clearTokens();
      return false;
    }

    saveTokens(payload);
    return true;
  } catch {
    clearTokens();
    return false;
  }
}

export async function getCurrentUser() {
  const token = getAccessToken();

  if (!token) {
    return null;
  }

  let response = await fetch(`${API_URL}/api/auth/me`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (response.status === 401) {
    const refreshed = await refreshSession();

    if (!refreshed) {
      return null;
    }

    response = await fetch(`${API_URL}/api/auth/me`, {
      headers: {
        Authorization: `Bearer ${getAccessToken()}`,
      },
    });
  }

  const payload = await parseResponse(response);

  if (!response.ok) {
    throw new Error(
      getErrorMessage(payload, `Session check failed: ${response.status}`)
    );
  }

  return payload;
}

export async function logout() {
  const refreshToken = getRefreshToken();

  try {
    if (refreshToken) {
      await fetch(`${API_URL}/api/auth/logout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    }
  } finally {
    clearTokens();
  }
}

export async function authenticatedFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const accessToken = getAccessToken();

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  let response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 401 && getRefreshToken()) {
    const refreshed = await refreshSession();

    if (refreshed) {
      const retryHeaders = new Headers(options.headers || {});
      retryHeaders.set(
        "Authorization",
        `Bearer ${getAccessToken()}`
      );

      response = await fetch(url, {
        ...options,
        headers: retryHeaders,
      });
    }
  }

  return response;
}

export { API_URL };
