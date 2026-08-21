"use client";

import { useState } from "react";
import { api, apiText, copyToClipboard } from "@/lib/api";
import { useRadar } from "@/lib/RadarContext";

/** Copy / YouTube / Spotify for one playlist, shown above its songs. */
export default function ExportButtons({
  playlist,
  youtube = { configured: false, connected: false },
  onNeedsSpotify,
  onNeedsYouTube,
}) {
  const { notify } = useRadar();
  const [busy, setBusy] = useState("");

  async function copy() {
    const text = await apiText(`/playlists/${playlist.id}/text`);
    const ok = await copyToClipboard(text);
    notify(ok ? `"${playlist.name}" copied.` : "Could not copy.", !ok);
  }

  async function saveToYoutube() {
    setBusy("yt");
    notify(`Creating "${playlist.name}" on your YouTube account...`);
    try {
      const data = await api(`/playlists/${playlist.id}/youtube-save`, "POST");
      if (data.url) {
        window.open(data.url, "_blank");

        let message;
        if (data.created) {
          message = `Created "${playlist.name}" on YouTube with ${data.added} songs.`;
        } else if (data.added) {
          message = `Added ${data.added} new song${data.added === 1 ? "" : "s"} to "${playlist.name}" on YouTube; ${data.already} were already there.`;
        } else {
          message = `"${playlist.name}" on YouTube is already up to date, all ${data.already} songs.`;
        }
        if (data.missing?.length) message += ` Not found on YouTube: ${data.missing.join(", ")}.`;
        if (data.error) message += ` ${data.error}`;
        notify(message, Boolean(data.error));
      } else {
        notify(data.error || "Could not save the playlist.", true);
      }
    } finally {
      setBusy("");
    }
  }

  async function toYoutube() {
    if (youtube.configured && youtube.connected) {
      await saveToYoutube();
      return;
    }
    // Opened during the click, or the popup blocker swallows it.
    const tab = window.open("", "_blank");
    setBusy("yt");
    notify("Looking the songs up on YouTube...");
    try {
      const data = await api(`/playlists/${playlist.id}/youtube`, "POST");
      if (data.urls?.length) {
        if (tab) tab.location = data.urls[0];
        else window.open(data.urls[0], "_blank");
        // A YouTube link holds 50 songs, so a longer playlist arrives split.
        for (const url of data.urls.slice(1)) window.open(url, "_blank");

        let message =
          data.urls.length > 1
            ? `${data.found} songs opened as ${data.urls.length} YouTube lists of 50 — that is all one link holds.`
            : `Opened with ${data.found} of ${data.total} songs.`;
        if (data.missing?.length) message += ` Not found: ${data.missing.join(", ")}.`;
        notify(message + " Press Save on YouTube to keep them.");
      } else {
        if (tab) tab.close();
        notify(data.error || "Could not build the playlist.", true);
      }
    } finally {
      setBusy("");
    }
  }

  async function toSpotify() {
    const status = await api("/spotify/status");
    if (!status.configured || !status.connected) {
      onNeedsSpotify?.();
      notify(
        status.configured
          ? "Connect Spotify first, in the panel below."
          : "Set your Spotify client id first, in the panel below.",
        true
      );
      return;
    }

    setBusy("sp");
    notify(`Creating "${playlist.name}" in your Spotify account...`);
    try {
      const data = await api(`/playlists/${playlist.id}/spotify`, "POST");
      if (data.url) {
        window.open(data.url, "_blank");
        let message = `Created in Spotify with ${data.found} of ${data.total} songs.`;
        if (data.missing?.length) {
          message += ` Not found: ${data.missing.join(", ")}.`;
        }
        notify(message);
      } else {
        notify(data.error || "Could not create the Spotify playlist.", true);
      }
    } finally {
      setBusy("");
    }
  }

  const empty = playlist.songs.length === 0;

  return (
    <div className="exports">
      <button className="btn sp" onClick={toSpotify} disabled={empty || busy === "sp"}>
        {busy === "sp" ? "Creating..." : "Spotify"}
      </button>
      <button
        className="btn yt"
        onClick={toYoutube}
        disabled={empty || busy === "yt"}
        title={
          youtube.connected
            ? "Create this playlist on your YouTube account"
            : "Open the songs as a temporary YouTube list. Connect an account to save them for keeps."
        }
      >
        {busy === "yt" ? "Working..." : youtube.connected ? "Save to YouTube" : "YouTube"}
      </button>
      {youtube.connected ? null : (
        <button className="btn" onClick={onNeedsYouTube} title="Connect a YouTube account">
          ⚙
        </button>
      )}
      <button className="btn" onClick={copy} disabled={empty}>
        Copy
      </button>
    </div>
  );
}
