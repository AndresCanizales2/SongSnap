"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useRadar } from "@/lib/RadarContext";
import EditableName from "@/components/EditableName";

export default function PlaylistsPage() {
  const router = useRouter();
  const {
    playlists,
    activeId,
    loaded,
    createPlaylist,
    renamePlaylist,
    deletePlaylist,
    setActive,
  } = useRadar();
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const [confirming, setConfirming] = useState(null);

  async function create() {
    const value = name.trim();
    if (!value) return;
    const playlist = await createPlaylist(value, true);
    setName("");
    setNaming(false);
    if (playlist) router.push("/listen");
  }

  async function listenInto(playlist) {
    if (await setActive(playlist.id)) router.push("/listen");
  }

  return (
    <main className="shell">
      <div className="section-head">
        <h2>My playlists</h2>
        <div className="tools">
          <button className="btn accent" onClick={() => setNaming(!naming)}>
            New playlist
          </button>
        </div>
      </div>

      {naming ? (
        <div className="picker">
          <div className="label">Name the new playlist</div>
          <div className="field">
            <input
              type="text"
              placeholder="Playlist name"
              maxLength={80}
              value={name}
              autoFocus
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") create();
                if (event.key === "Escape") setNaming(false);
              }}
            />
            <button className="btn accent" onClick={create}>
              Create and listen into it
            </button>
          </div>
        </div>
      ) : null}

      {!loaded ? null : playlists.length === 0 ? (
        <div className="empty">
          No playlists yet. Create one and SongRadar starts filling it.
        </div>
      ) : (
        <div className="grid">
          {playlists.map((playlist) => (
            <div
              className={
                playlist.id === activeId ? "tile active" : "tile"
              }
              key={playlist.id}
            >
              <div className="tile-top">
                <EditableName
                  name={playlist.name}
                  onRename={(value) => renamePlaylist(playlist.id, value)}
                  className="tile-name"
                />
                {playlist.id === activeId ? (
                  <span className="tag">
                    <span className="rec" /> collecting
                  </span>
                ) : null}
              </div>

              <div className="tile-meta">
                {playlist.songs.length}{" "}
                {playlist.songs.length === 1 ? "song" : "songs"} · created{" "}
                {playlist.created}
              </div>

              <div className="tile-songs">
                {playlist.songs
                  .slice(-3)
                  .reverse()
                  .map((song) => (
                    <div className="tile-song" key={song.id}>
                      {song.artist} — {song.title}
                    </div>
                  ))}
                {playlist.songs.length === 0 ? (
                  <div className="tile-song dim">Still empty</div>
                ) : null}
              </div>

              <div className="tile-tools">
                <Link className="btn" href={`/playlist?id=${playlist.id}`}>
                  Open
                </Link>
                {playlist.id === activeId ? null : (
                  <button className="btn accent" onClick={() => listenInto(playlist)}>
                    Listen into it
                  </button>
                )}
                {confirming === playlist.id ? (
                  <>
                    <button
                      className="btn"
                      style={{ color: "var(--danger)" }}
                      onClick={() => {
                        setConfirming(null);
                        deletePlaylist(playlist);
                      }}
                    >
                      Really delete
                    </button>
                    <button className="btn" onClick={() => setConfirming(null)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    className="btn"
                    onClick={() => setConfirming(playlist.id)}
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
