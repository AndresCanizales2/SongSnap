"use client";

import PlayButton from "./PlayButton";
import AddToPlaylist from "./AddToPlaylist";

const BAR_HEIGHTS = [8, 16, 10, 18, 6];

export default function NowPlaying({ song }) {
  const playing = Boolean(song && song.title);

  return (
    <div className={playing ? "now live" : "now"}>
      <div className="now-label">Now playing</div>

      <div className={playing ? "bars" : "bars paused"}>
        {BAR_HEIGHTS.map((height, index) => (
          <i key={index} style={{ height, animationDelay: `${index * 0.12}s` }} />
        ))}
      </div>

      {playing && song.cover ? (
        <div className="cover">
          {/* The cover comes from the recognition service, so it is a remote
              URL Next cannot optimize: a plain img is the right call. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={song.cover} alt="" />
        </div>
      ) : null}

      {playing ? (
        <>
          <div className="song-title">{song.title}</div>
          <div className="song-artist">{song.artist}</div>

          {song.source ? (
            <div className="badge">
              {song.source === "Microphone"
                ? "picked up by the mic"
                : "picked up from system audio"}
            </div>
          ) : null}

          <div className="now-tools">
            <PlayButton song={song} big />
            <AddToPlaylist song={song} />
          </div>
        </>
      ) : (
        <div className="song-title">
          <span className="waiting">Waiting for music...</span>
        </div>
      )}
    </div>
  );
}
