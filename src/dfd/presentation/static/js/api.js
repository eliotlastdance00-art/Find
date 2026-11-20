// HTTP client: bearer-token auth, JSON errors, upload progress and SSE over fetch.
const TOKEN_KEY = "dfd.session";

export class ApiError extends Error {
  constructor(status, code, params = {}) {
    super(code);
    this.status = status;
    this.code = code;
    this.params = params;
  }
}

function loadSession() {
  try {
    const saved = JSON.parse(localStorage.getItem(TOKEN_KEY) || "null");
    return saved && saved.expires > Date.now() ? saved : null;
  } catch {
    return null;
  }
}

let session = loadSession();
let onUnauthorized = () => {};

export const auth = {
  get token() { return session?.token ?? null; },
  get user() { return session?.user ?? null; },
  set(data) {
    session = { token: data.token, user: data.user, expires: Date.now() + data.expires_in * 1000 };
    localStorage.setItem(TOKEN_KEY, JSON.stringify(session));
  },
  clear() {
    session = null;
    localStorage.removeItem(TOKEN_KEY);
  },
  onUnauthorized(handler) { onUnauthorized = handler; },
};

async function parseError(response) {
  let code = "error";
  let params = {};
  try {
    const body = await response.json();
    code = body.error?.code ?? code;
    params = body.error?.params ?? {};
  } catch { /* non-JSON error body */ }
  if (response.status === 401 && code === "not_authenticated") {
    auth.clear();
    onUnauthorized();
  }
  return new ApiError(response.status, code, params);
}

function headers(extra = {}) {
  return session ? { Authorization: `Bearer ${session.token}`, ...extra } : extra;
}

export async function request(method, path, body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: headers(body ? { "Content-Type": "application/json" } : {}),
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network");
  }
  if (!response.ok) throw await parseError(response);
  return response.status === 204 ? null : response.json();
}

export const api = {
  meta: () => request("GET", "/api/meta"),
  login: (username, password) => request("POST", "/api/auth/login", { username, password }),
  register: (username, password) => request("POST", "/api/auth/register", { username, password }),
  me: () => request("GET", "/api/auth/me"),
  scan: (id) => request("GET", `/api/scans/${encodeURIComponent(id)}`),
  start: (id) => request("POST", `/api/scans/${encodeURIComponent(id)}/start`),
  remove: (id) => request("DELETE", `/api/scans/${encodeURIComponent(id)}`),
  stats: () => request("GET", "/api/stats"),
  history(params = {}) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) if (value !== "" && value != null) query.set(key, value);
    return request("GET", `/api/scans?${query}`);
  },

  // XMLHttpRequest because fetch cannot report upload progress.
  upload(file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const form = new FormData();
      form.append("file", file, file.name);
      xhr.open("POST", "/api/scans");
      if (session) xhr.setRequestHeader("Authorization", `Bearer ${session.token}`);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(event.loaded / event.total);
      };
      xhr.onerror = () => reject(new ApiError(0, "network"));
      xhr.onload = () => {
        let body = null;
        try { body = JSON.parse(xhr.responseText); } catch { /* handled below */ }
        if (xhr.status >= 200 && xhr.status < 300 && body) return resolve(body);
        if (xhr.status === 401) { auth.clear(); onUnauthorized(); }
        reject(new ApiError(xhr.status, body?.error?.code ?? "error", body?.error?.params ?? {}));
      };
      xhr.send(form);
    });
  },

  // Server-sent events read through fetch so the Authorization header can be sent.
  async events(id, onEvent, signal) {
    const response = await fetch(`/api/scans/${encodeURIComponent(id)}/events`, { headers: headers(), signal });
    if (!response.ok) throw await parseError(response);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const chunk = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        for (const line of chunk.split("\n")) {
          if (line.startsWith("data:")) onEvent(JSON.parse(line.slice(5)));
        }
      }
    }
  },
};

// URLs for <img>, <video>, <iframe> and downloads, authorised by the scan's media token.
export const media = {
  source: (scan) => `/api/scans/${scan.id}/source?t=${encodeURIComponent(scan.media_token)}`,
  file: (scan, name) => `/api/scans/${scan.id}/files/${encodeURIComponent(name)}?t=${encodeURIComponent(scan.media_token)}`,
  report: (scan, language, download = false) =>
    `/api/scans/${scan.id}/report.pdf?lang=${language}&t=${encodeURIComponent(scan.media_token)}${download ? "&download=true" : ""}`,
};
