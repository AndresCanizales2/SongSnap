// In the packaged app the service also serves this page, so same-origin calls
// are the default. NEXT_PUBLIC_API_URL points somewhere else during development.
const CONFIGURED = process.env.NEXT_PUBLIC_API_URL || "";

export const API = CONFIGURED;

export function wsUrl() {
  if (CONFIGURED) return CONFIGURED.replace(/^http/, "ws") + "/ws";
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws`;
}

export async function api(path, method = "GET", body) {
  const options = { method };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const response = await fetch(API + path, options);
  return response.json();
}

export async function apiText(path) {
  const response = await fetch(API + path);
  return response.text();
}

export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // The clipboard API needs a secure context: localhost is one, a LAN IP is
    // not, so fall back to the old selection trick there.
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    area.remove();
    return ok;
  }
}

export function matches(song, query) {
  if (!query) return true;
  const needle = query.toLowerCase();
  return (
    (song.title || "").toLowerCase().includes(needle) ||
    (song.artist || "").toLowerCase().includes(needle)
  );
}
