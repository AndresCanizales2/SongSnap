"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { api, wsUrl } from "./api";

const RadarContext = createContext(null);

export function useRadar() {
  const value = useContext(RadarContext);
  if (!value) throw new Error("useRadar must be used inside RadarProvider");
  return value;
}

export function RadarProvider({ children }) {
  const [connected, setConnected] = useState(false);
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const [playlists, setPlaylists] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [toasts, setToasts] = useState([]);
  const toastId = useRef(0);

  const notify = useCallback((message, bad = false) => {
    const id = ++toastId.current;
    setToasts((list) => [...list, { id, message, bad }]);
    setTimeout(
      () => setToasts((list) => list.filter((t) => t.id !== id)),
      bad ? 7000 : 4500
    );
  }, []);

  // One socket for the whole app: it survives navigation between views
  // because the provider lives in the layout.
  useEffect(() => {
    let socket;
    let retry;
    let stopped = false;

    function open() {
      socket = new WebSocket(wsUrl());
      socket.onopen = () => setConnected(true);
      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "song") {
          setCurrent(data.current);
          setHistory(data.history || []);
        }
        if (data.type === "playlists") {
          setPlaylists(data.playlists || []);
          setActiveId(data.active || null);
          setLoaded(true);
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!stopped) retry = setTimeout(open, 2000);
      };
    }

    open();
    return () => {
      stopped = true;
      clearTimeout(retry);
      if (socket) socket.close();
    };
  }, []);

  // First paint should not wait for the socket handshake.
  useEffect(() => {
    api("/playlists")
      .then((data) => {
        setPlaylists(data.playlists || []);
        setActiveId(data.active || null);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  const createPlaylist = useCallback(
    async (name, activate = false) => {
      const data = await api("/playlists", "POST", { name, activate });
      if (data.playlist) notify(`Playlist "${data.playlist.name}" created.`);
      return data.playlist || null;
    },
    [notify]
  );

  const renamePlaylist = useCallback(
    async (id, name) => {
      const data = await api(`/playlists/${id}`, "PATCH", { name });
      if (data.error) notify(data.error, true);
      else notify(`Renamed to "${name}".`);
    },
    [notify]
  );

  const deletePlaylist = useCallback(
    async (playlist) => {
      const data = await api(`/playlists/${playlist.id}`, "DELETE");
      if (data.error) notify(data.error, true);
      else notify(`"${playlist.name}" deleted.`);
    },
    [notify]
  );

  const setActive = useCallback(
    async (playlistId) => {
      const data = await api("/active", "POST", { playlist_id: playlistId || "" });
      if (data.error) notify(data.error, true);
      return !data.error;
    },
    [notify]
  );

  const removeSong = useCallback(
    async (playlistId, songId) => {
      const data = await api(`/playlists/${playlistId}/songs/${songId}`, "DELETE");
      if (data.error) notify(data.error, true);
    },
    [notify]
  );

  const addSong = useCallback(
    async (playlistId, song) => {
      const data = await api(`/playlists/${playlistId}/songs`, "POST", song);
      if (data.error) {
        notify(data.error, true);
        return;
      }
      notify(
        data.added
          ? `"${song.title}" added.`
          : `"${song.title}" is ${data.reason}.`,
        !data.added
      );
    },
    [notify]
  );

  const active = playlists.find((pl) => pl.id === activeId) || null;

  return (
    <RadarContext.Provider
      value={{
        connected,
        current,
        history,
        playlists,
        active,
        activeId,
        loaded,
        toasts,
        notify,
        createPlaylist,
        renamePlaylist,
        deletePlaylist,
        setActive,
        removeSong,
        addSong,
      }}
    >
      {children}
    </RadarContext.Provider>
  );
}
