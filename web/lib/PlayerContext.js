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
 * "jump to that song and keep going", and the list can show which one is on.
 */
export function PlayerProvider({ children }) {
  const [source, setSource] = useState(null); // the playlist (or song) being played
  const [queue, setQueue] = useState([]); // [{ song_id, video_id, title, artist }]
  const [index, setIndex] = useState(0);
  const [seekTo, setSeekTo] = useState(null); // index the panel should jump to
  const [loadingId, setLoadingId] = useState(null);
  const [failed, setFailed] = useState("");

  // Stable, or the panel's effect would re-run on every render.
  const clearSeek = useCallback(() => setSeekTo(null), []);

  const close = useCallback(() => {
    setSource(null);
    setQueue([]);
    setIndex(0);
    setSeekTo(null);
  }, []);

  const loadQueue = useCallback(async (playlist) => {
    const data = await api(`/playlists/${playlist.id}/videos`, "POST").catch(() => ({
      error: "The recognition service is not reachable.",
    }));
    return data;
  }, []);

  /** Play a playlist from a given song, or from the top. */
  const playPlaylist = useCallback(
    async (playlist, songId = null) => {
      // Already loaded? Then this is just a jump, no reload, no reset.
      if (source?.id === playlist.id && queue.length) {
        const target = songId
          ? queue.findIndex((entry) => entry.song_id === songId)
          : 0;
        if (target >= 0) {
          setSeekTo(target);
          setIndex(target);
          return { jumped: true };
        }
      }

      setFailed("");
      setLoadingId(songId || playlist.id);
      const data = await loadQueue(playlist);
      setLoadingId(null);

      if (!data.queue || !data.queue.length) {
        setFailed(songId || playlist.id);
        return { error: data.error || "No video found for this playlist." };
      }

      const start = songId
        ? Math.max(0, data.queue.findIndex((entry) => entry.song_id === songId))
        : 0;

      setSource({ id: playlist.id, name: playlist.name });
      setQueue(data.queue);
      setIndex(start);
      setSeekTo(start);
      return { found: data.found, total: data.total, missing: data.missing };
    },
    [source, queue, loadQueue]
  );

  /** A single song that is not part of the playlist being collected. */
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
      setIndex(0);
      setSeekTo(0);
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
        index,
        seekTo,
        currentSongId,
        loadingId,
        failed,
        playPlaylist,
        playSingle,
        close,
        setIndex,
        clearSeek,
      }}
    >
      {children}
    </PlayerContext.Provider>
  );
}
