import { authenticatedFetch, API_URL } from "./auth.js";

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    return response.json();
  }

  return response.text();
}

function errorMessage(payload, fallback) {
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

export async function apiFetch(path, options = {}) {
  const response = await authenticatedFetch(`${API_URL}${path}`, options);
  const payload = await parseResponse(response);

  if (!response.ok) {
    throw new Error(
      errorMessage(payload, `Request failed: ${response.status}`)
    );
  }

  return payload;
}

export async function getBackendHealth() {
  const response = await fetch(`${API_URL}/health`);

  if (!response.ok) {
    throw new Error(`Backend request failed: ${response.status}`);
  }

  return response.json();
}
