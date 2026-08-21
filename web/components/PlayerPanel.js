"use client";

import { useEffect, useRef } from "react";
import { usePlayer } from "@/lib/PlayerContext";
import { loadYouTubeApi } from "@/lib/youtube";

/**
 * The one player, above the list.
 *
 * The player is always built around a real video id, with the rest of the
 * playlist in `playlist`: that is the embed URL YouTube actually plays. An
 * empty player told to loadPlaylist afterwards ends up on `embed/` with no
 * video and never starts, which is exactly what this used to do wrong.
 *
 * Starting from a different song rebuilds the player from there, so the queue
 * that follows is always the rest of the list.
 */
export default function PlayerPanel() {
  const { source, queue, start, index, setIndex, close } = usePlayer();
  const holder = useRef(null);
  const player = useRef(null);
  const builtFor = useRef("");

  const ids = queue.slice(start).map((entry) => entry.video_id);
  const key = ids.join(",");

  useEffect(() => {
    if (!source || !ids.length) return;
    if (builtFor.current === key) return;

    let dropped = false;

    loadYouTubeApi().then((YT) => {
      if (dropped || !YT || !holder.current) return;

      if (player.current) {
        try {
          player.current.destroy();
        } catch {
          // already gone
        }
        player.current = null;
      }

      // destroy() removes the iframe, so give the API a fresh node to fill.
      const node = document.createElement("div");
      holder.current.innerHTML = "";
      holder.current.appendChild(node);

      builtFor.current = key;
      player.current = new YT.Player(node, {
        videoId: ids[0],
        playerVars: {
          autoplay: 1,
          rel: 0,
          ...(ids.length > 1 ? { playlist: ids.slice(1).join(",") } : {}),
        },
        events: {
          onStateChange: (event) => {
            const at = event.target.getPlaylistIndex?.();
            // The player's queue starts at `start`, the list's does not.
            if (typeof at === "number" && at >= 0) setIndex(start + at);
          },
        },
      });
    });

    return () => {
      dropped = true;
    };
  }, [source, ids, key, start, setIndex]);

  // Nothing playing: tear the player down so it stops making sound.
  useEffect(() => {
    if (source) return;
    if (player.current) {
      try {
        player.current.destroy();
      } catch {
        // already gone
      }
    }
    player.current = null;
    builtFor.current = "";
    if (holder.current) holder.current.innerHTML = "";
  }, [source]);

  if (!source || !queue.length) return null;

  const now = queue[index] || queue[start];

  return (
    <div className="player">
      <div className="player-frame" ref={holder} />
      <div className="player-bar">
        <div className="player-now">
          <span className="player-pos">
            {index + 1}/{queue.length}
          </span>
          <span className="player-title">{now.title}</span>
          <span className="player-artist">{now.artist}</span>
        </div>
        <button className="btn" onClick={close}>
          Close player
        </button>
      </div>
    </div>
  );
}
