"use client";

import { useCallback, useEffect, useRef } from "react";
import { usePlayer } from "@/lib/PlayerContext";
import { loadYouTubeApi } from "@/lib/youtube";

/**
 * The one player, at the top of the list. It keeps the whole playlist queued,
 * so it rolls on to the next song by itself and reports which one is playing.
 */
export default function PlayerPanel() {
  const { source, queue, index, seekTo, clearSeek, setIndex, close } = usePlayer();
  const holder = useRef(null);
  const player = useRef(null);
  const ready = useRef(false);
  const loadedKey = useRef("");
  const pending = useRef(null);

  const key = queue.map((entry) => entry.video_id).join(",");

  // The player's methods only exist once YouTube says it is ready, so work
  // asked for before that is parked here and applied on arrival.
  const applyPending = useCallback(
    (target) => {
      const job = pending.current;
      if (!job || !target) return;
      pending.current = null;

      if (loadedKey.current !== job.key) {
        target.loadPlaylist({ playlist: job.ids, index: job.index });
        loadedKey.current = job.key;
      } else {
        target.playVideoAt(job.index);
      }
      clearSeek();
    },
    [clearSeek]
  );

  useEffect(() => {
    if (!source || !queue.length) return;
    let dropped = false;

    pending.current = {
      key,
      ids: queue.map((entry) => entry.video_id),
      index: seekTo === null ? 0 : seekTo,
    };

    loadYouTubeApi().then((YT) => {
      if (dropped || !YT || !holder.current) return;

      if (!player.current) {
        player.current = new YT.Player(holder.current, {
          playerVars: { autoplay: 1, rel: 0 },
          events: {
            onReady: (event) => {
              ready.current = true;
              applyPending(event.target);
            },
            onStateChange: (event) => {
              const at = event.target.getPlaylistIndex?.();
              if (typeof at === "number" && at >= 0) setIndex(at);
            },
          },
        });
        return;
      }

      if (ready.current) applyPending(player.current);
    });

    return () => {
      dropped = true;
    };
  }, [source, queue, key, seekTo, applyPending, setIndex]);

  // Tear the player down when nothing is playing, so it stops making sound.
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
    ready.current = false;
    loadedKey.current = "";
    pending.current = null;
  }, [source]);

  if (!source || !queue.length) return null;

  const now = queue[index] || queue[0];

  return (
    <div className="player">
      <div className="player-frame">
        <div ref={holder} />
      </div>
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
