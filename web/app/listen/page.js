"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRadar } from "@/lib/RadarContext";
import { usePlayer } from "@/lib/PlayerContext";
import NowPlaying from "@/components/NowPlaying";
import EditableName from "@/components/EditableName";
import PlayButton from "@/components/PlayButton";
import PlayerPanel from "@/components/PlayerPanel";
import PlayAllButton from "@/components/PlayAllButton";
import ExportButtons from "@/components/ExportButtons";
import SpotifyPanel from "@/components/SpotifyPanel";

export default function ListenPage() {
  const router = useRouter();
  const {
    current,
    history,
    active,
    loaded,
    connected,
    renamePlaylist,
    removeSong,
    addSong,
  } = useRadar();
  const { currentSongId } = usePlayer();
  const [showSpotify, setShowSpotify] = useState(false);
  const [spotify, setSpotify] = useState({ configured: false, connected: false });

  // Nothing to listen into means back to the opening screen.
  useEffect(() => {
    if (loaded && !active) router.replace("/");
  }, [loaded, active, router]);

  if (!active) return <main className="shell" />;

  const songs = [...active.songs].reverse(); // newest first
  const inPlaylist = new Set(
    active.songs.map((s) => `${s.artist.toLowerCase()}|${s.title.toLowerCase()}`)
  );
  const notCollected = history.filter(
    (s) => !inPlaylist.has(`${s.artist.toLowerCase()}|${s.title.toLowerCase()}`)
  );

  return (
    <main className="shell">
      <NowPlaying song={current} />

      <section className="section">
        <div className="playlist-bar">
          <div className="playlist-bar-name">
            <EditableName
              name={active.name}
              onRename={(name) => renamePlaylist(active.id, name)}
              className="h2"
            />
            <span className="count">
              {active.songs.length} {active.songs.length === 1 ? "song" : "songs"}
            </span>
          </div>
          <div className="bar-tools">
            <PlayAllButton playlist={active} />
            <ExportButtons
              playlist={active}
              onNeedsSpotify={() => setShowSpotify(true)}
            />
          </div>
        </div>

        <PlayerPanel />

        {showSpotify ? (
          <SpotifyPanel
            status={spotify}
            setStatus={setSpotify}
            notify={(m, bad) => console.log(m, bad)}
          />
        ) : null}

        {songs.length === 0 ? (
          <div className="empty">
            {connected
              ? "Listening. Whatever plays next lands here."
              : "Waiting for the recognition service..."}
          </div>
        ) : (
          <div className="rows">
            {songs.map((song) => (
              <div key={song.id}>
                <div className={song.id === currentSongId ? "row playing" : "row"}>
                  <div className="thumb">
                    {song.cover ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={song.cover} alt="" />
                    ) : null}
                  </div>
                  <div className="meta">
                    <div className="t">{song.title}</div>
                    <div className="a">{song.artist}</div>
                  </div>
                  <PlayButton song={song} playlist={active} />
                  <button
                    className="icon-btn danger"
                    title="Remove from this playlist"
                    onClick={() => removeSong(active.id, song.id)}
                  >
                    ×
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {notCollected.length ? (
        <section className="section">
          <div className="section-head">
            <h2>Recognized earlier, not in this playlist</h2>
          </div>
          <div className="rows">
            {notCollected.map((song) => (
              <div key={song.id}>
                <div className="row">
                  <div className="thumb">
                    {song.cover ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={song.cover} alt="" />
                    ) : null}
                  </div>
                  <div className="meta">
                    <div className="t">{song.title}</div>
                    <div className="a">{song.artist}</div>
                  </div>
                  <div className="time">{song.time}</div>
                  <PlayButton song={song} />
                  <button
                    className="icon-btn"
                    title={`Add to ${active.name}`}
                    onClick={() => addSong(active.id, song)}
                  >
                    +
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <Link href="/playlists" className="nav-link">
        See all my playlists →
      </Link>
    </main>
  );
}
