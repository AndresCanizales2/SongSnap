"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRadar } from "@/lib/RadarContext";

export default function StartPage() {
  const router = useRouter();
  const { active, playlists, loaded, connected, createPlaylist, setActive } =
    useRadar();
  const [name, setName] = useState("");
  const [working, setWorking] = useState(false);

  // Already collecting into something? Then this screen has nothing to ask.
  useEffect(() => {
    if (loaded && active) router.replace("/listen");
  }, [loaded, active, router]);

  const typed = name.trim().toLowerCase();
  // Typing filters what you already have, so you carry on with a playlist
  // instead of ending up with two called almost the same.
  const matching = typed
    ? playlists.filter((pl) => pl.name.toLowerCase().includes(typed))
    : playlists;
  const exact = playlists.find((pl) => pl.name.toLowerCase() === typed);

  async function start() {
    const value = name.trim();
    if (!value || working) return;
    setWorking(true);
    // Same name as one you have? Carry on with that one.
    if (exact) {
      if (await setActive(exact.id)) router.push("/listen");
      else setWorking(false);
      return;
    }
    const playlist = await createPlaylist(value, true);
    if (playlist) router.push("/listen");
    else setWorking(false);
  }

  async function continueWith(playlist) {
    if (await setActive(playlist.id)) router.push("/listen");
  }

  return (
    <main className="start">
      <div className="start-top">
        <Link href="/playlists" className="btn">
          My playlists
          {playlists.length ? <span className="pill">{playlists.length}</span> : null}
        </Link>
      </div>

      <div className="start-inner">
        <div className={connected ? "dish big" : "dish big idle"} />

        <h1 className="start-title">
          Song<span>Radar</span>
        </h1>
        <p className="start-sub">
          Name the playlist you are starting. Everything recognized from now on
          goes into it.
        </p>

        <div className="start-field">
          <input
            type="text"
            placeholder="For example: Friday night"
            maxLength={80}
            value={name}
            autoFocus
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") start();
            }}
          />
          <button
            className="btn accent big"
            onClick={start}
            disabled={!name.trim() || working}
          >
            {working ? "Starting..." : exact ? "Carry on with it" : "Start listening"}
          </button>
        </div>

        {exact ? (
          <p className="start-hint">
            You already have a playlist called <b>{exact.name}</b> — it will
            carry on filling up instead of creating another one.
          </p>
        ) : null}

        {!connected ? (
          <p className="start-warn">
            No connection to the recognition service yet. Start it with{" "}
            <b>start.bat</b> — this page reconnects on its own.
          </p>
        ) : null}

        {loaded ? (
          <div className="start-existing">
            <div className="label">
              {playlists.length
                ? typed
                  ? `My playlists matching "${name.trim()}"`
                  : "or carry on with one you already have"
                : "You have no playlists yet"}
            </div>

            {matching.length ? (
              <div className="options">
                {matching.slice(0, 8).map((playlist) => (
                  <button
                    key={playlist.id}
                    className="btn"
                    onClick={() => continueWith(playlist)}
                    title={`Keep filling "${playlist.name}"`}
                  >
                    {playlist.name}
                    <span className="pill">{playlist.songs.length}</span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="hint">
                {playlists.length
                  ? "None of your playlists match that name — press Start listening to create it."
                  : "The first name you type becomes your first playlist."}
              </div>
            )}

            {playlists.length ? (
              <Link href="/playlists" className="nav-link">
                See all my playlists →
              </Link>
            ) : null}
          </div>
        ) : null}
      </div>
    </main>
  );
}
