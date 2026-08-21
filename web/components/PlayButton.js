"use client";

import { usePlayer } from "@/lib/PlayerContext";
import { useRadar } from "@/lib/RadarContext";

/**
 * Play one song in the player at the top. When the song belongs to a playlist,
 * the rest of that playlist stays queued behind it.
 */
export default function PlayButton({ song, playlist = null, big = false }) {
  const { playPlaylist, playSingle, currentSongId, loadingId, failed } = usePlayer();
  const { notify } = useRadar();

  const isPlaying = currentSongId === song.id;
  const isLoading = loadingId === song.id;
  const isFailed = failed === song.id;

  const label = isLoading
    ? "Looking for the video..."
    : isFailed
      ? "No video found for this song"
      : isPlaying
        ? "Playing now"
        : playlist
          ? "Play from here"
          : "Play it on YouTube";

  async function onClick(event) {
    event.stopPropagation();
    const result = playlist
      ? await playPlaylist(playlist, song.id)
      : await playSingle(song);
    if (result?.error) notify(result.error, true);
  }

  return (
    <button
      className={`play-btn${big ? " big" : ""}${isPlaying ? " on" : ""}${isFailed ? " failed" : ""}`}
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={isLoading}
    >
      {isLoading ? (
        <span className="spinner" />
      ) : isPlaying ? (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="5" y="4" width="3.5" height="16" rx="1">
            <animate attributeName="height" values="16;7;16" dur="0.9s" repeatCount="indefinite" />
          </rect>
          <rect x="10.5" y="4" width="3.5" height="16" rx="1">
            <animate attributeName="height" values="10;16;10" dur="0.9s" repeatCount="indefinite" />
          </rect>
          <rect x="16" y="4" width="3.5" height="16" rx="1">
            <animate attributeName="height" values="16;9;16" dur="1.1s" repeatCount="indefinite" />
          </rect>
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M8 5.5v13a1 1 0 0 0 1.5.87l11-6.5a1 1 0 0 0 0-1.74l-11-6.5A1 1 0 0 0 8 5.5z" />
        </svg>
      )}
      {big ? <span>{isPlaying ? "Playing" : "Play"}</span> : null}
    </button>
  );
}
