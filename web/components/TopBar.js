"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useRadar } from "@/lib/RadarContext";

export default function TopBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { connected, active, playlists, createPlaylist, setActive } = useRadar();
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");

  // The opening screen is deliberately bare.
  if (pathname === "/") return null;

  async function create() {
    const value = name.trim();
    if (!value) return;
    const playlist = await createPlaylist(value, true);
    setName("");
    setNaming(false);
    if (playlist) router.push("/listen");
  }

  return (
    <>
      <nav className="topbar">
        <Link href="/listen" className="brand">
          <span className={connected ? "dish" : "dish idle"} />
          <strong>
            Song<span>Radar</span>
          </strong>
        </Link>

        <div className="nav-links">
          <Link
            href="/listen"
            className={pathname === "/listen" ? "nav-link on" : "nav-link"}
          >
            Listening
          </Link>
          <Link
            href="/playlists"
            className={
              pathname.startsWith("/playlists") ? "nav-link on" : "nav-link"
            }
          >
            My playlists
            {playlists.length ? (
              <span className="pill">{playlists.length}</span>
            ) : null}
          </Link>
        </div>

        <div className="nav-right">
          <button className="btn accent" onClick={() => setNaming(!naming)}>
            New playlist
          </button>
        </div>
      </nav>

      {naming ? (
        <div className="shell" style={{ paddingBottom: 0 }}>
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
        </div>
      ) : null}

      {active ? (
        <div className="shell" style={{ paddingBottom: 0, paddingTop: 16 }}>
          <div className="collecting">
            <span className="rec" /> Collecting into <b>{active.name}</b>
            <button
              className="btn"
              style={{ marginLeft: "auto" }}
              onClick={() => setActive(null)}
            >
              Stop collecting
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
