"use client";

import { useCallback, useEffect, useState } from "react";
import { API, api } from "@/lib/api";

export default function SpotifyPanel({ status, setStatus, notify }) {
  const [clientId, setClientId] = useState("");
  const [editing, setEditing] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api("/spotify/status"));
    } catch {
      // the service being down is already reported by the page banner
    }
  }, [setStatus]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function saveId() {
    const value = clientId.trim();
    if (!value) return;
    const data = await api("/spotify/config", "POST", { client_id: value });
    setClientId("");
    if (data.error) {
      notify(data.error, true);
      return;
    }
    setEditing(false);
    await refresh();
    notify("Client id saved. Now press Connect Spotify.");
  }

  function connect() {
    // Spotify's own login page, in its own tab: no password ever reaches here.
    window.open(`${API}/spotify/login`, "_blank");
    notify("Authorize it in the Spotify tab, then come back.");
    setTimeout(refresh, 6000);
  }

  async function disconnect() {
    await api("/spotify/disconnect", "POST");
    await refresh();
    notify("Spotify disconnected.");
  }

  const needsSetup = !status.configured || editing;

  return (
    <div className="picker setup">
      <div className="label">
        Spotify —{" "}
        {!status.configured
          ? "not set up"
          : status.connected
            ? status.user
              ? `connected as ${status.user}`
              : "connected"
            : "client id saved, not connected"}
      </div>

      {needsSetup ? (
        <>
          <p>
            To create playlists in your own account, register a free app once.
            You log in on Spotify&apos;s page — SongRadar never sees your
            password.
          </p>
          <ol>
            <li>
              Open{" "}
              <a
                href="https://developer.spotify.com/dashboard"
                target="_blank"
                rel="noopener noreferrer"
              >
                developer.spotify.com/dashboard
              </a>{" "}
              and create an app
            </li>
            <li>
              Add this exact redirect URI:{" "}
              <code>{status.redirect_uri || `${API}/spotify/callback`}</code>
            </li>
            <li>
              Tick <b>Web API</b>, save, and copy the app&apos;s <b>Client ID</b>
            </li>
          </ol>
          <div className="field">
            <input
              type="text"
              placeholder="Client ID"
              maxLength={120}
              value={clientId}
              onChange={(event) => setClientId(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") saveId();
              }}
            />
            <button className="btn sp" onClick={saveId}>
              Save
            </button>
          </div>
        </>
      ) : (
        <div className="field">
          {status.connected ? null : (
            <button className="btn sp" onClick={connect}>
              Connect Spotify
            </button>
          )}
          <button className="btn" onClick={() => setEditing(true)}>
            Change client id
          </button>
          {status.connected ? (
            <button className="btn" onClick={disconnect}>
              Disconnect
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}
