"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useRadar } from "@/lib/RadarContext";
import { usePlayer } from "@/lib/PlayerContext";
import EditableName from "@/components/EditableName";
import PlayButton from "@/components/PlayButton";
import PlayerPanel from "@/components/PlayerPanel";
import PlayAllButton from "@/components/PlayAllButton";
import ExportButtons from "@/components/ExportButtons";
import SpotifyPanel from "@/components/SpotifyPanel";
import YouTubePanel from "@/components/YouTubePanel";

function PlaylistView() {
  const id = useSearchParams().get("id");
  const router = useRouter();
  const {
    playlists,
    activeId,
    loaded,
    renamePlaylist,
    removeSong,
    setActive,
    notify,
  } = useRadar();
  const { currentSongId } = usePlayer();
  const [showSpotify, setShowSpotify] = useState(false);
  const [spotify, setSpotify] = useState({ configured: false, connected: false });
  const [showYoutube, setShowYoutube] = useState(false);
  const [youtube, setYoutube] = useState({ configured: false, connected: false });

  const playlist = playlists.find((pl) => pl.id === id);

  if (!playlist) {
    return (
      <main className="shell">
        <div className="empty">
          {loaded ? "That playlist no longer exists." : "Loading..."}
        </div>
        <Link href="/playlists" className="nav-link">
          ← My playlists
        </Link>
      </main>
    );
  }

  const songs = [...playlist.songs].reverse();

  async function listenInto() {
    if (await setActive(playlist.id)) router.push("/listen");
  }

  return (
    <main className="shell">
      <Link href="/playlists" className="nav-link">
        ← My playlists
      </Link>

      <div className="playlist-bar detail">
        <div className="playlist-bar-name">
          <EditableName
            name={playlist.name}
            onRename={(value) => renamePlaylist(playlist.id, value)}
            className="h1"
          />
          <span className="count">
            {playlist.songs.length}{" "}
            {playlist.songs.length === 1 ? "song" : "songs"}
            {playlist.id === activeId ? " · collecting now" : ""}
          </span>
        </div>
        <div className="bar-tools">
          <PlayAllButton playlist={playlist} />
          <ExportButtons
            playlist={playlist}
            onNeedsSpotify={() => setShowSpotify(true)}
            onNeedsYouTube={() => setShowYoutube(true)}
          />
        </div>
      </div>

      <PlayerPanel />

      {playlist.id === activeId ? null : (
        <button className="btn accent" onClick={listenInto}>
          Listen into this playlist
        </button>
      )}

      {showYoutube ? (
        <YouTubePanel status={youtube} setStatus={setYoutube} notify={notify} />
      ) : null}

      {showSpotify ? (
        <SpotifyPanel status={spotify} setStatus={setSpotify} notify={notify} />
      ) : null}

      <section className="section" style={{ marginTop: 20 }}>
        {songs.length === 0 ? (
          <div className="empty">
            Empty. Listen into it, or add songs from the listening screen.
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
                  <div className="time">{song.added}</div>
                  <PlayButton song={song} playlist={playlist} />
                  <button
                    className="icon-btn danger"
                    title="Remove from this playlist"
                    onClick={() => removeSong(playlist.id, song.id)}
                  >
                    ×
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default function PlaylistPage() {
  // useSearchParams needs a boundary to fall back to while it resolves.
  return (
    <Suspense fallback={<main className="shell" />}>
      <PlaylistView />
    </Suspense>
  );
}
