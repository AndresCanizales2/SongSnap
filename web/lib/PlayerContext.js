"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { api } from "./api";

const PlayerContext = createContext(null);

export function usePlayer() {
  const value = useContext(PlayerContext);
  if (!value) throw new Error("usePlayer must be used inside PlayerProvider");
  return value;
}

/**
 * One player for the whole page, always shown at the top of the list.
 *
 * The queue is the playlist itself, so playing a single song is really
 * "start here and keep going", and the list can show which one is on.
 */
export function PlayerProvider({ children }) {
  const [source, setSource] = useState(null); // the playlist (or song) being played
  const [queue, setQueue] = useState([]); // [{ song_id, video_id, title, artist }]
  const [start, setStart] = useState(0); // where the player's queue begins
  const [index, setIndex] = useState(0); // which song is playing, in `queue`
  const [loadingId, setLoadingId] = useState(null);
  const [failed, setFailed] = useState("");

  const close = useCallback(() => {
    setSource(null);
    setQueue([]);
    setStart(0);
    setIndex(0);
  }, []);

  /** Play a playlist from a given song, or from the top. */
  const playPlaylist = useCallback(
    async (playlist, songId = null) => {
      // Already loaded? Then only the starting point changes.
      if (source?.id === playlist.id && queue.length) {
        const at = songId ? queue.findIndex((entry) => entry.song_id === songId) : 0;
        if (at >= 0) {
          setStart(at);
          setIndex(at);
          return { jumped: true };
        }
      }

      setFailed("");
      setLoadingId(songId || playlist.id);
      const data = await api(`/playlists/${playlist.id}/videos`, "POST").catch(() => ({
        error: "The recognition service is not reachable.",
      }));
      setLoadingId(null);

      if (!data.queue || !data.queue.length) {
        setFailed(songId || playlist.id);
        return { error: data.error || "No video found for this playlist." };
      }

      const at = songId
        ? Math.max(0, data.queue.findIndex((entry) => entry.song_id === songId))
        : 0;

      setSource({ id: playlist.id, name: playlist.name });
      setQueue(data.queue);
      setStart(at);
      setIndex(at);
      return {
        found: data.found,
        total: data.total,
        missing: data.missing,
        leftOut: data.left_out,
      };
    },
    [source, queue]
  );

  /** A single song, on its own. */
  const playSingle = useCallback(
    async (song) => {
      if (source?.id === song.id) {
        close();
        return { closed: true };
      }

      setFailed("");
      setLoadingId(song.id);
      const data = await api(
        `/video?artist=${encodeURIComponent(song.artist || "")}&title=${encodeURIComponent(song.title || "")}`
      ).catch(() => ({ error: "The recognition service is not reachable." }));
      setLoadingId(null);

      if (!data.id) {
        setFailed(song.id);
        return { error: data.error || "No video found for this song." };
      }

      setSource({ id: song.id, name: song.title });
      setQueue([
        { song_id: song.id, video_id: data.id, title: song.title, artist: song.artist },
      ]);
      setStart(0);
      setIndex(0);
      return { single: true };
    },
    [source, close]
  );

  const currentSongId = queue[index]?.song_id || null;

  return (
    <PlayerContext.Provider
      value={{
        source,
        queue,
        start,
        index,
        currentSongId,
        loadingId,
        failed,
        playPlaylist,
        playSingle,
        close,
        setIndex,
      }}
    >
      {children}
    </PlayerContext.Provider>
  );
}
