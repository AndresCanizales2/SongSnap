"use client";

import { usePlayer } from "@/lib/PlayerContext";
import { useRadar } from "@/lib/RadarContext";

/** Play a whole playlist from the top, in the player above the list. */
export default function PlayAllButton({ playlist }) {
  const { playPlaylist, close, source, loadingId, failed } = usePlayer();
  const { notify } = useRadar();

  const isOpen = source?.id === playlist.id;
  const isLoading = loadingId === playlist.id;
  const empty = playlist.songs.length === 0;

  async function onClick() {
    if (isOpen) {
      close();
      return;
    }
    const result = await playPlaylist(playlist);
    if (result?.error) {
      notify(result.error, true);
      return;
    }
    if (result?.found) {
      let message = `Playing ${result.found} of ${result.total} songs.`;
      if (result.missing?.length) message += ` Not on YouTube: ${result.missing.join(", ")}.`;
      notify(message);
    }
  }

  return (
    <button
      className={`btn accent${failed === playlist.id ? " failed" : ""}`}
      onClick={onClick}
      disabled={empty || isLoading}
      title={empty ? "This playlist is empty" : isOpen ? "Close the player" : "Play every song, in order"}
    >
      {isLoading ? "Looking up videos..." : isOpen ? "Stop playing" : "▶ Play all"}
    </button>
  );
}
