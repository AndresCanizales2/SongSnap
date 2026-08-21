"use client";

import { useState } from "react";
import { useRadar } from "@/lib/RadarContext";

/**
 * "Add to playlist" next to a song: lists every playlist as a button, and
 * takes a name for a new one right there.
 */
export default function AddToPlaylist({ song, label = "Add to playlist" }) {
  const { playlists, active, addSong, createPlaylist } = useRadar();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");

  if (!song || !song.title) return null;

  async function addToNew() {
    const value = name.trim();
    if (!value) return;
    const playlist = await createPlaylist(value);
    setName("");
    setOpen(false);
    if (playlist) await addSong(playlist.id, song);
  }

  async function addTo(playlist) {
    setOpen(false);
    await addSong(playlist.id, song);
  }

  return (
    <>
      <button className="btn accent" onClick={() => setOpen(!open)}>
        {label}
        {playlists.length ? <span className="pill">{playlists.length}</span> : null}
      </button>

      {open ? (
        <div className="picker song-picker">
          <div className="label">Add &ldquo;{song.title}&rdquo; to</div>

          {playlists.length ? (
            <div className="options">
              {playlists.map((playlist) => (
                <button
                  key={playlist.id}
                  className={playlist.id === active?.id ? "btn accent" : "btn"}
                  onClick={() => addTo(playlist)}
                >
                  {playlist.name}
                  <span className="pill">{playlist.songs.length}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="hint">No playlists yet — name one below.</div>
          )}

          <div className="field">
            <input
              type="text"
              placeholder="New playlist name"
              maxLength={80}
              value={name}
              autoFocus
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") addToNew();
                if (event.key === "Escape") setOpen(false);
              }}
            />
            <button className="btn" onClick={addToNew}>
              Create &amp; add
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
