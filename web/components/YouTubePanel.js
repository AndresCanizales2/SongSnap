"use client";

import { useCallback, useEffect, useState } from "react";
import { API, api } from "@/lib/api";

/**
 * Connecting a YouTube account, so playlists can be saved for keeps instead of
 * opened as throwaway links.
 */
export default function YouTubePanel({ status, setStatus, notify }) {
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [editing, setEditing] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api("/youtube/status"));
    } catch {
      // the page banner already reports the service being down
    }
  }, [setStatus]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function saveCredentials() {
    const id = clientId.trim();
    const secret = clientSecret.trim();
    if (!id || !secret) return;
    const data = await api("/youtube/config", "POST", {
      client_id: id,
      client_secret: secret,
    });
    setClientId("");
    setClientSecret("");
    if (data.error) {
      notify(data.error, true);
      return;
    }
    setEditing(false);
    await refresh();
    notify("Credentials saved. Now press Connect YouTube.");
  }

  function connect() {
    // Google's own consent screen, in its own tab.
    window.open(`${API}/youtube/login`, "_blank");
    notify("Authorize it in the Google tab, then come back.");
    setTimeout(refresh, 8000);
  }

  async function forget() {
    await api("/youtube/config", "DELETE");
    setEditing(false);
    await refresh();
    notify("Credentials removed from this machine.");
  }

  async function disconnect() {
    await api("/youtube/disconnect", "POST");
    await refresh();
    notify("YouTube disconnected.");
  }

  const needsSetup = !status.configured || editing;

  return (
    <div className="picker setup">
      <div className="label">
        YouTube account —{" "}
        {!status.configured
          ? "not set up"
          : status.connected
            ? status.channel
              ? `connected as ${status.channel}`
              : "connected"
            : "credentials saved, not connected"}
      </div>

      {needsSetup ? (
        <>
          <p>
            Without this, the YouTube button opens throwaway lists that YouTube
            will not let you keep. Connecting an account lets SongRadar create
            the playlist for real, and top it up with new songs later instead
            of making another copy. Free, but it takes a few minutes once.
          </p>
          <ol>
            <li>
              Open{" "}
              <a
                href="https://console.cloud.google.com/projectcreate"
                target="_blank"
                rel="noopener noreferrer"
              >
                Google Cloud
              </a>{" "}
              and create a project
            </li>
            <li>
              Enable{" "}
              <a
                href="https://console.cloud.google.com/apis/library/youtube.googleapis.com"
                target="_blank"
                rel="noopener noreferrer"
              >
                YouTube Data API v3
              </a>
            </li>
            <li>
              On the OAuth consent screen pick <b>External</b>, then open{" "}
              <b>Audience</b> and add your own Google address under{" "}
              <b>Test users</b>. Skipping this is what makes Google answer{" "}
              <i>Error 403: access_denied</i>.
            </li>
            <li>
              Create an <b>OAuth client ID</b> of type <b>Web application</b>{" "}
              with this redirect URI:{" "}
              <code>{status.redirect_uri || `${API}/youtube/callback`}</code>
            </li>
            <li>
              Copy the <b>Client ID</b> and <b>Client secret</b> it gives you
            </li>
          </ol>
          <div className="field">
            <input
              type="text"
              placeholder="Client ID"
              maxLength={200}
              value={clientId}
              onChange={(event) => setClientId(event.target.value)}
            />
          </div>
          <div className="field" style={{ marginTop: 6 }}>
            <input
              type="password"
              placeholder="Client secret"
              maxLength={200}
              value={clientSecret}
              onChange={(event) => setClientSecret(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") saveCredentials();
              }}
            />
            <button className="btn yt" onClick={saveCredentials}>
              Save
            </button>
          </div>
          <p style={{ marginTop: 10 }}>
            Google will warn that the app is not verified — it is your own app,
            so choose <b>Advanced → Go to SongRadar</b>. While the project stays
            in testing, Google expires the authorization after 7 days and you
            reconnect with one click. Pressing <b>Publish app</b> on the
            Audience page keeps the warning but stops the weekly expiry, and
            lets any Google account in without the test user list.
          </p>
        </>
      ) : (
        <div className="field">
          {status.connected ? null : (
            <button className="btn yt" onClick={connect}>
              Connect YouTube
            </button>
          )}
          <button className="btn" onClick={() => setEditing(true)}>
            Change credentials
          </button>
          <button className="btn" onClick={forget} title="Remove the credentials from this machine">
            Forget credentials
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
