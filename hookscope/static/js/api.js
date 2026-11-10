// Thin wrapper over the local API. Every write carries the app header the server requires.

const HEADERS = { "X-Hookscope": "1" };

async function request(method, path, body) {
  const init = { method, headers: { ...HEADERS } };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error("Hookscope isn't running. Double-click Hookscope.command to start it.");
  }
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const detail = data && (typeof data.detail === "string" ? data.detail : data.detail?.[0]?.msg);
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

function safeJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body = {}) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  patch: (path, body) => request("PATCH", path, body),
  del: (path) => request("DELETE", path),
  upload: (path, formData) => request("POST", path, formData),
};
