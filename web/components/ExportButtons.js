"use client";

import { useState } from "react";
import { api, apiText, copyToClipboard } from "@/lib/api";
import { useRadar } from "@/lib/RadarContext";

/** Copy / YouTube / Spotify for one playlist, shown above its songs. */
export default function ExportButtons({ playlist, onNeedsSpotify }) {
  const { notify } = useRadar();
  const [busy, setBusy] = useState("");

  async function copy() {
    const text = await apiText(`/playlists/${playlist.id}/text`);
    const ok = await copyToClipboard(text);
    notify(ok ? `"${playlist.name}" copied.` : "Could not copy.", !ok);
  }

  async function toYoutube() {
    // Opened during the click, or the popup blocker swallows it.
    const tab = window.open("", "_blank");
    setBusy("yt");
    notify("Looking the songs up on YouTube...");
    try {
      const data = await api(`/playlists/${playlist.id}/youtube`, "POST");
      if (data.url) {
        if (tab) tab.location = data.url;
        else window.open(data.url, "_blank");
        notify(
          `Opened with ${data.found} of ${data.total} songs. Press Save on YouTube to keep it.`
        );
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
      <button className="btn yt" onClick={toYoutube} disabled={empty || busy === "yt"}>
        {busy === "yt" ? "Searching..." : "YouTube"}
      </button>
      <button className="btn" onClick={copy} disabled={empty}>
        Copy
      </button>
    </div>
  );
}
