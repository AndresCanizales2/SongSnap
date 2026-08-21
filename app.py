import sys

# Windows console UTF-8 setup
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import base64
import hashlib
import io
import json
import os
import re
import signal
import threading
import urllib.parse
import uuid
import webbrowser
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime

import numpy as np
import pyaudiowpatch as pyaudio
import requests
import uvicorn
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
)
from pydub import AudioSegment
from ShazamAPI import Shazam

# ShazamAPI decodes the sample with pydub without declaring a format, which
# makes pydub shell out to ffmpeg. We always feed it PCM WAV, so declare the
# format and let pydub use its built-in wave reader (no ffmpeg needed).
_pydub_from_file = AudioSegment.from_file


def _from_file_wav(file, format=None, *args, **kwargs):
    return _pydub_from_file(file, format=format or "wav", *args, **kwargs)


AudioSegment.from_file = staticmethod(_from_file_wav)

# -- Where this runs ----------------------------------------------------------
FROZEN = getattr(sys, "frozen", False)


def data_dir() -> str:
    """Where our own files are kept: beside the exe, or beside the source."""
    if FROZEN:
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def asset_dir() -> str:
    """Where read-only bundled files live (PyInstaller unpacks into a temp)."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


PORT = int(os.environ.get("SONGRADAR_PORT", "8000"))

# The exported interface, served by this same process when it is there. During
# development Next serves it instead, on its own port.
WEB_DIR = os.path.join(asset_dir(), "web", "out")
BUNDLED_WEB = os.path.isdir(WEB_DIR)
WEB_PORT = int(os.environ.get("SONGRADAR_WEB_PORT", "3000"))
WEB_URL = f"http://127.0.0.1:{PORT}" if BUNDLED_WEB else f"http://localhost:{WEB_PORT}"


# -- State management --------------------------------------------------------
current_song = {"title": "", "artist": "", "cover": "", "time": "", "source": ""}
song_history = []
clients: list[WebSocket] = []
running = True
capture_sources: list[str] = []
capture_stopped = threading.Event()
_loop = None

# Playlists outlive the session, so they live on disk next to the script.
PLAYLISTS_FILE = os.path.join(data_dir(), "playlists.json")
playlists: list[dict] = []
# Everything recognized while a playlist is active lands in it, so the user
# names a playlist once and then just plays music.
active_playlist_id: str | None = None
_playlists_lock = threading.Lock()


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def load_playlists():
    global playlists, active_playlist_id
    try:
        with open(PLAYLISTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        playlists = data.get("playlists", []) if isinstance(data, dict) else []
        active_playlist_id = data.get("active") if isinstance(data, dict) else None
        if not find_playlist(active_playlist_id or ""):
            active_playlist_id = None
        print(f"  Playlists: {len(playlists)} loaded", flush=True)
    except FileNotFoundError:
        playlists = []
    except Exception as e:
        # A corrupt file must not stop the app; keep it aside instead of
        # overwriting it, so nothing is lost silently.
        print(f"  Could not read {os.path.basename(PLAYLISTS_FILE)}: {e}", flush=True)
        try:
            os.replace(PLAYLISTS_FILE, PLAYLISTS_FILE + ".broken")
            print(f"  Kept the unreadable file as {os.path.basename(PLAYLISTS_FILE)}.broken", flush=True)
        except OSError:
            pass
        playlists = []


def save_playlists():
    """Write through a temp file so a crash mid-write cannot truncate it."""
    tmp = PLAYLISTS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"playlists": playlists, "active": active_playlist_id},
                f,
                ensure_ascii=False,
                indent=2,
            )
        os.replace(tmp, PLAYLISTS_FILE)
    except Exception as e:
        print(f"  Could not save playlists: {e}", flush=True)


def find_playlist(playlist_id: str) -> dict | None:
    return next((pl for pl in playlists if pl["id"] == playlist_id), None)


def append_song(playlist: dict, title: str, artist: str, cover: str = "") -> bool:
    """Add a song unless the playlist already has it. Caller holds the lock."""
    already = any(
        s["title"].lower() == title.lower() and s["artist"].lower() == artist.lower()
        for s in playlist["songs"]
    )
    if already:
        return False

    playlist["songs"].append(
        {
            "id": new_id(),
            "title": title,
            "artist": artist,
            "cover": cover,
            "added": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    )
    return True


# -- Shazam recognition ------------------------------------------------------
# A signature covers at most 8 seconds of audio (Shazam.MAX_TIME_SECONDS), and
# building one costs ~0.5s of CPU per second of audio (the fingerprint runs in
# pure Python) plus ~1.2s of network. Feeding exactly one signature's worth is
# the best precision per second spent; a longer clip only buys a second
# signature over leftover audio at double the cost.
MAX_SIGNATURES = 1


def recognize_from_wav_bytes(wav_bytes: bytes) -> dict | None:
    try:
        shazam = Shazam(wav_bytes)
        for attempt, (offset, result) in enumerate(shazam.recognizeSong(), 1):
            if result.get("matches"):
                track = result["track"]
                return {
                    "title": track.get("title", "Unknown"),
                    "artist": track.get("subtitle", "Unknown"),
                    "cover": track.get("images", {}).get("coverarthq", ""),
                }
            if attempt >= MAX_SIGNATURES:
                break
    except Exception as e:
        print(f"  Recognition error: {e}", flush=True)
    return None


# -- Find loopback device ----------------------------------------------------
def get_loopback_device(p: pyaudio.PyAudio):
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        print("  WASAPI not found.", flush=True)
        return None

    default_output = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    print(f"  Default output: {default_output['name']}", flush=True)

    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev.get("isLoopbackDevice") and dev["name"].startswith(
            default_output["name"]
        ):
            print(f"  Loopback device: {dev['name']}", flush=True)
            return dev

    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev.get("isLoopbackDevice"):
            print(f"  Loopback device (fallback): {dev['name']}", flush=True)
            return dev
    return None


def get_microphone_device(p: pyaudio.PyAudio):
    """Default recording device — never a loopback endpoint."""
    try:
        dev = p.get_default_input_device_info()
    except (OSError, IOError):
        return None
    if dev.get("isLoopbackDevice") or int(dev.get("maxInputChannels", 0)) < 1:
        return None
    print(f"  Microphone: {dev['name']}", flush=True)
    return dev


# -- Audio capture + recognition loop -----------------------------------------
TARGET_RATE = 48000
CHUNK = 1024

# Each source keeps a rolling window and we recognize every RECOGNIZE_EVERY
# seconds, so consecutive attempts overlap instead of chopping a song into
# unrelated slices. The window matches what one Shazam signature can hold.
WINDOW_SECONDS = 8
RECOGNIZE_EVERY = 5
MIN_SECONDS = 4

# The mic runs quieter than the loopback stream, so it gets its own gate.
SILENCE_THRESHOLD = 500
MIC_SILENCE_THRESHOLD = 200

# Quiet audio wastes int16 resolution before the fingerprint is taken. Lift it
# towards full scale, but never so hard that room hiss becomes the signal.
TARGET_PEAK = 0.6 * 32767
MAX_GAIN = 6.0


def _rms(mono: np.ndarray) -> float:
    if not len(mono):
        return 0.0
    return float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))


def _normalize(mono: np.ndarray) -> np.ndarray:
    peak = float(np.abs(mono).max()) if len(mono) else 0.0
    if peak < 1.0:
        return mono
    gain = min(TARGET_PEAK / peak, MAX_GAIN)
    return mono * gain if gain > 1.0 else mono


class SourceRecorder:
    """Reads one input device into a rolling window on its own thread."""

    def __init__(self, p: pyaudio.PyAudio, device: dict, label: str, silence_threshold: int):
        self.label = label
        self.silence_threshold = silence_threshold
        self.channels = max(1, int(device["maxInputChannels"]))
        self.rate = int(device["defaultSampleRate"])
        self._frames: list[bytes] = []
        self._lock = threading.Lock()
        self._stream = p.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=device["index"],
            frames_per_buffer=CHUNK,
        )
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        max_chunks = int(self.rate / CHUNK * WINDOW_SECONDS)
        while running:
            try:
                data = self._stream.read(CHUNK, exception_on_overflow=False)
            except Exception as e:
                print(f"  {self.label} read error: {e}", flush=True)
                time.sleep(0.5)
                continue
            with self._lock:
                self._frames.append(data)
                if len(self._frames) > max_chunks:
                    del self._frames[:-max_chunks]

    def snapshot(self) -> np.ndarray:
        """The last WINDOW_SECONDS as mono float32 at TARGET_RATE.

        The window is kept, not drained: the next attempt overlaps this one.
        """
        with self._lock:
            frames = list(self._frames)
        if not frames:
            return np.zeros(0, dtype=np.float32)

        samples = np.frombuffer(b"".join(frames), dtype=np.int16)
        if self.channels > 1:
            usable = len(samples) - len(samples) % self.channels
            samples = samples[:usable].reshape(-1, self.channels).mean(axis=1)
        mono = samples.astype(np.float32)

        if self.rate != TARGET_RATE and len(mono):
            count = int(len(mono) * TARGET_RATE / self.rate)
            mono = np.interp(
                np.linspace(0, len(mono), count, endpoint=False),
                np.arange(len(mono)),
                mono,
            ).astype(np.float32)
        return mono

    def close(self) -> bool:
        """Close the stream. False if the reader thread would not let go.

        A loopback device with nothing playing blocks inside stream.read()
        forever, so the reader can outlive the request to stop. Tearing the
        stream down from under that read segfaults the interpreter, and the
        process is on its way out anyway, so leave it to the OS instead.
        """
        self._thread.join(timeout=1.0)
        if self._thread.is_alive():
            return False
        try:
            self._stream.stop_stream()
            self._stream.close()
        except Exception:
            pass
        return True


def open_sources(p: pyaudio.PyAudio) -> list[SourceRecorder]:
    """Microphone first, system audio second — that is the listening order.

    SONGSNAP_SOURCES=system or =mic narrows it down to a single source.
    """
    wanted = os.environ.get("SONGSNAP_SOURCES", "both").strip().lower()
    sources = []

    if wanted in ("both", "mic"):
        device = get_microphone_device(p)
        if device:
            sources.append(SourceRecorder(p, device, "Microphone", MIC_SILENCE_THRESHOLD))
        else:
            print("  Microphone not found — mic input disabled.", flush=True)

    if wanted in ("both", "system"):
        device = get_loopback_device(p)
        if device:
            sources.append(SourceRecorder(p, device, "System audio", SILENCE_THRESHOLD))
        else:
            print("  Loopback device not found — system audio disabled.", flush=True)

    return sources


def to_wav(mono: np.ndarray, sample_width: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(sample_width)
        wf.setframerate(TARGET_RATE)
        wf.writeframes(np.clip(mono, -32768, 32767).astype(np.int16).tobytes())
    return buffer.getvalue()


def audio_capture_loop():
    p = pyaudio.PyAudio()
    sources = open_sources(p)
    if not sources:
        print("  No capture device available!", flush=True)
        p.terminate()
        capture_stopped.set()
        return

    capture_sources[:] = [source.label for source in sources]
    sample_width = p.get_sample_size(pyaudio.paInt16)
    print(f"  Listening order: {' then '.join(s.label for s in sources)}", flush=True)
    print(f"  Config: mono, {TARGET_RATE}Hz, {WINDOW_SECONDS}s window every {RECOGNIZE_EVERY}s", flush=True)
    print("  Play some music!", flush=True)
    print()

    cycle_started = time.time()
    try:
        capture_cycles(sources, sample_width, cycle_started)
    finally:
        closed = [source.close() for source in sources]
        if all(closed):
            p.terminate()
        capture_stopped.set()


def capture_cycles(sources, sample_width, cycle_started):
    global current_song, song_history

    while running:
        try:
            # Pace from the start of the cycle: recognizing a source already
            # costs several seconds, and that time should count towards the
            # interval instead of being added on top of it.
            wait = RECOGNIZE_EVERY - (time.time() - cycle_started)
            deadline = time.time() + max(0.0, wait)
            while running and time.time() < deadline:
                time.sleep(0.1)
            if not running:
                break
            cycle_started = time.time()

            # One source at a time, in order, so each fingerprint sees a clean
            # signal. Mixing them would blur both into a worse match.
            result, matched_on = None, ""
            for source in sources:
                if not running:
                    break
                mono = source.snapshot()
                if len(mono) < MIN_SECONDS * TARGET_RATE:
                    continue
                if _rms(mono) < source.silence_threshold:
                    continue

                result = recognize_from_wav_bytes(to_wav(_normalize(mono), sample_width))
                if result:
                    matched_on = source.label
                    break

            if result and (
                result["title"] != current_song.get("title")
                or result["artist"] != current_song.get("artist")
            ):
                now = datetime.now().strftime("%H:%M:%S")
                current_song = {**result, "id": new_id(), "time": now, "source": matched_on}
                song_history.insert(0, current_song.copy())
                song_history[:] = song_history[:50]

                print(f"  >> [{now}] ({matched_on}) {result['artist']} - {result['title']}", flush=True)
                broadcast_song()

                if collect_into_active(current_song):
                    broadcast_playlists()

                # Find its video now, in the background: by the time anyone
                # presses play the whole playlist is already resolved.
                threading.Thread(
                    target=youtube_video_id,
                    args=(f"{result['artist']} {result['title']}".strip(),),
                    daemon=True,
                ).start()

        except Exception as e:
            print(f"  Capture error: {e}", flush=True)
            time.sleep(1)


# -- YouTube account ----------------------------------------------------------
# The temporary watch_videos links above need no account and cannot be kept.
# Saving a real playlist means the YouTube Data API, which means Google OAuth.
#
# Google, unlike Spotify, wants a client secret even with PKCE, so both halves
# live in youtube.json beside the app. PKCE is used anyway: it costs nothing
# and the authorization code is useless to anyone who intercepts it.
YOUTUBE_CONFIG_FILE = os.path.join(data_dir(), "youtube.json")
YOUTUBE_REDIRECT_URI = f"http://127.0.0.1:{PORT}/youtube/callback"
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube"
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"

# playlists.insert and every playlistItems.insert cost 50 units of the 10,000
# a day a new project gets, so roughly 195 songs a day in total.
YOUTUBE_UNITS_PER_INSERT = 50

youtube_config: dict = {}
_youtube_token = {"access_token": "", "expires_at": 0.0}
_youtube_pending: dict[str, str] = {}
_youtube_lock = threading.Lock()


def load_youtube_config():
    global youtube_config
    try:
        with open(YOUTUBE_CONFIG_FILE, encoding="utf-8") as f:
            youtube_config = json.load(f)
    except FileNotFoundError:
        youtube_config = {}
    except Exception as e:
        print(f"  Could not read {os.path.basename(YOUTUBE_CONFIG_FILE)}: {e}", flush=True)
        youtube_config = {}

    for key, variable in (("client_id", "YOUTUBE_CLIENT_ID"), ("client_secret", "YOUTUBE_CLIENT_SECRET")):
        value = os.environ.get(variable, "").strip()
        if value:
            youtube_config[key] = value

    if youtube_config.get("client_id"):
        state = "connected" if youtube_config.get("refresh_token") else "not connected yet"
        print(f"  YouTube account: credentials set, {state}", flush=True)


def save_youtube_config():
    """Holds a refresh token and a client secret: same care as the rest."""
    tmp = YOUTUBE_CONFIG_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(youtube_config, f, ensure_ascii=False, indent=2)
        os.replace(tmp, YOUTUBE_CONFIG_FILE)
    except Exception as e:
        print(f"  Could not save the YouTube config: {e}", flush=True)


def youtube_login_url() -> str | None:
    client_id = youtube_config.get("client_id")
    if not client_id:
        return None

    verifier = base64.urlsafe_b64encode(os.urandom(48)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode().rstrip("=")
    state = new_id()
    with _youtube_lock:
        _youtube_pending.clear()
        _youtube_pending[state] = verifier

    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": YOUTUBE_REDIRECT_URI,
            "response_type": "code",
            "scope": YOUTUBE_SCOPE,
            # offline + consent is what makes Google hand back a refresh token.
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
        }
    )
    return f"{GOOGLE_AUTH}?{query}"


def youtube_exchange_code(code: str, state: str) -> str:
    """Swap the callback code for tokens. Returns an error message, or ''."""
    with _youtube_lock:
        verifier = _youtube_pending.pop(state, None)
    if not verifier:
        return "This login link is no longer valid. Start the connection again."

    try:
        resp = requests.post(
            GOOGLE_TOKEN,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": YOUTUBE_REDIRECT_URI,
                "client_id": youtube_config.get("client_id", ""),
                "client_secret": youtube_config.get("client_secret", ""),
                "code_verifier": verifier,
            },
            timeout=20,
        )
        data = resp.json()
    except Exception as e:
        return f"Could not reach Google: {e}"

    if "refresh_token" not in data:
        detail = data.get("error_description") or data.get("error") or ""
        if data.get("access_token"):
            detail = detail or (
                "Google returned no refresh token. Remove SongRadar from your "
                "Google account's third-party access and connect again."
            )
        return detail or "Google refused the login."

    youtube_config["refresh_token"] = data["refresh_token"]
    _youtube_token["access_token"] = data.get("access_token", "")
    _youtube_token["expires_at"] = time.time() + data.get("expires_in", 3600) - 60

    channel = youtube_get("/channels", {"part": "snippet", "mine": "true"})
    items = (channel or {}).get("items", [])
    if items:
        youtube_config["channel"] = items[0]["snippet"].get("title", "")
    save_youtube_config()
    return ""


def youtube_access_token() -> str | None:
    if _youtube_token["access_token"] and time.time() < _youtube_token["expires_at"]:
        return _youtube_token["access_token"]

    refresh_token = youtube_config.get("refresh_token")
    if not (refresh_token and youtube_config.get("client_id")):
        return None

    try:
        resp = requests.post(
            GOOGLE_TOKEN,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": youtube_config.get("client_id", ""),
                "client_secret": youtube_config.get("client_secret", ""),
            },
            timeout=20,
        )
        data = resp.json()
    except Exception as e:
        print(f"  YouTube token refresh failed: {e}", flush=True)
        return None

    if "access_token" not in data:
        print(f"  YouTube token refresh rejected: {data.get('error_description', data)}", flush=True)
        return None

    _youtube_token["access_token"] = data["access_token"]
    _youtube_token["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
    return _youtube_token["access_token"]


def google_error(resp) -> str:
    """Google's own words, which name the quota when that is the problem."""
    try:
        error = resp.json().get("error", {})
        message = error.get("message", "")
        reasons = [e.get("reason", "") for e in error.get("errors", [])]
    except Exception:
        message, reasons = (resp.text or "").strip()[:200], []

    if "quotaExceeded" in reasons or "quota" in message.lower():
        return (
            "YouTube's daily quota is spent. A project gets 10,000 units a day "
            "and each song costs 50, so about 195 songs. It resets at midnight "
            "Pacific time."
        )
    return f"YouTube says: {message}" if message else f"YouTube replied {resp.status_code}."


def youtube_get(path: str, params: dict, token: str | None = None):
    token = token or _youtube_token["access_token"]
    try:
        resp = requests.get(
            YOUTUBE_API + path,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        return resp.json() if resp.status_code < 400 else None
    except Exception as e:
        print(f"  YouTube GET {path} failed: {e}", flush=True)
        return None


def youtube_save_playlist(playlist: dict) -> dict:
    """Create a real playlist on the account and fill it, in order."""
    token = youtube_access_token()
    if not token:
        return {"error": "YouTube is not connected."}

    queries = [f"{s['artist']} {s['title']}".strip() for s in playlist["songs"]]
    ids, missing = resolve_video_ids(queries)
    if not ids:
        return {"error": "No song of this playlist could be found on YouTube."}

    headers = {"Authorization": f"Bearer {token}"}
    try:
        created = requests.post(
            f"{YOUTUBE_API}/playlists",
            params={"part": "snippet,status"},
            headers=headers,
            json={
                "snippet": {"title": playlist["name"], "description": "Created by SongRadar"},
                "status": {"privacyStatus": "private"},
            },
            timeout=25,
        )
    except Exception as e:
        return {"error": f"Could not create the playlist: {e}"}

    if created.status_code >= 400:
        return {"error": google_error(created)}

    playlist_id = created.json().get("id")
    if not playlist_id:
        return {"error": "YouTube did not return a playlist id."}

    # One request per song, in order, so the playlist reads as the list does.
    added = 0
    for video_id in ids:
        try:
            item = requests.post(
                f"{YOUTUBE_API}/playlistItems",
                params={"part": "snippet"},
                headers=headers,
                json={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
                timeout=25,
            )
        except Exception as e:
            return {
                "url": f"https://www.youtube.com/playlist?list={playlist_id}",
                "added": added,
                "total": len(queries),
                "missing": missing,
                "error": f"Stopped after {added} songs: {e}",
            }

        if item.status_code >= 400:
            return {
                "url": f"https://www.youtube.com/playlist?list={playlist_id}",
                "added": added,
                "total": len(queries),
                "missing": missing,
                "error": google_error(item),
            }
        added += 1

    return {
        "url": f"https://www.youtube.com/playlist?list={playlist_id}",
        "added": added,
        "total": len(queries),
        "missing": missing,
    }


# -- Spotify ------------------------------------------------------------------
# Creating a playlist in someone's account needs their authorization, so this
# runs the Authorization Code flow with PKCE: the user logs in on Spotify's own
# page and only a refresh token ever reaches us. PKCE means no client secret is
# involved, so the app only ever holds a client id, which is not a secret.
SPOTIFY_CONFIG_FILE = os.path.join(data_dir(), "spotify.json")
SPOTIFY_REDIRECT_URI = f"http://127.0.0.1:{PORT}/spotify/callback"
SPOTIFY_SCOPES = "playlist-modify-private playlist-modify-public"
SPOTIFY_ACCOUNTS = "https://accounts.spotify.com"
SPOTIFY_API = "https://api.spotify.com/v1"
SPOTIFY_TRACKS_PER_REQUEST = 100

spotify_config: dict = {}
_spotify_token = {"access_token": "", "expires_at": 0.0}
_spotify_pending: dict[str, str] = {}
_spotify_lock = threading.Lock()


def load_spotify_config():
    global spotify_config
    try:
        with open(SPOTIFY_CONFIG_FILE, encoding="utf-8") as f:
            spotify_config = json.load(f)
    except FileNotFoundError:
        spotify_config = {}
    except Exception as e:
        print(f"  Could not read {os.path.basename(SPOTIFY_CONFIG_FILE)}: {e}", flush=True)
        spotify_config = {}

    # An environment variable wins, so the id can be set without the UI.
    env_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    if env_id:
        spotify_config["client_id"] = env_id
    if spotify_config.get("client_id"):
        state = "connected" if spotify_config.get("refresh_token") else "not connected yet"
        print(f"  Spotify: client id set, {state}", flush=True)


def save_spotify_config():
    """Holds a refresh token, so it is written like the playlists file."""
    tmp = SPOTIFY_CONFIG_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(spotify_config, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SPOTIFY_CONFIG_FILE)
    except Exception as e:
        print(f"  Could not save the Spotify config: {e}", flush=True)


def spotify_login_url() -> str | None:
    client_id = spotify_config.get("client_id")
    if not client_id:
        return None

    verifier = base64.urlsafe_b64encode(os.urandom(48)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode().rstrip("=")
    state = new_id()
    with _spotify_lock:
        _spotify_pending.clear()  # only the newest login attempt is valid
        _spotify_pending[state] = verifier

    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": SPOTIFY_REDIRECT_URI,
            "scope": SPOTIFY_SCOPES,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
        }
    )
    return f"{SPOTIFY_ACCOUNTS}/authorize?{query}"


def spotify_exchange_code(code: str, state: str) -> str:
    """Swap the callback code for tokens. Returns an error message, or ''."""
    with _spotify_lock:
        verifier = _spotify_pending.pop(state, None)
    if not verifier:
        return "This login link is no longer valid. Start the connection again."

    try:
        resp = requests.post(
            f"{SPOTIFY_ACCOUNTS}/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": SPOTIFY_REDIRECT_URI,
                "client_id": spotify_config.get("client_id", ""),
                "code_verifier": verifier,
            },
            timeout=20,
        )
        data = resp.json()
    except Exception as e:
        return f"Could not reach Spotify: {e}"

    if "refresh_token" not in data:
        return data.get("error_description") or data.get("error") or "Spotify refused the login."

    spotify_config["refresh_token"] = data["refresh_token"]
    _spotify_token["access_token"] = data.get("access_token", "")
    _spotify_token["expires_at"] = time.time() + data.get("expires_in", 3600) - 60

    profile, _ = spotify_get("/me", _spotify_token["access_token"])
    if profile:
        spotify_config["user"] = profile.get("display_name") or profile.get("id", "")
    save_spotify_config()
    return ""


def spotify_access_token() -> str | None:
    if _spotify_token["access_token"] and time.time() < _spotify_token["expires_at"]:
        return _spotify_token["access_token"]

    refresh_token = spotify_config.get("refresh_token")
    client_id = spotify_config.get("client_id")
    if not (refresh_token and client_id):
        return None

    try:
        resp = requests.post(
            f"{SPOTIFY_ACCOUNTS}/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            timeout=20,
        )
        data = resp.json()
    except Exception as e:
        print(f"  Spotify token refresh failed: {e}", flush=True)
        return None

    if "access_token" not in data:
        print(f"  Spotify token refresh rejected: {data.get('error_description', data)}", flush=True)
        return None

    # Spotify hands out a new refresh token now and then; keep the latest one.
    if data.get("refresh_token"):
        spotify_config["refresh_token"] = data["refresh_token"]
        save_spotify_config()

    _spotify_token["access_token"] = data["access_token"]
    _spotify_token["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
    return _spotify_token["access_token"]


def spotify_error(resp) -> str:
    """Spotify's own words for a refusal, which are usually the whole story.

    Some refusals come back as JSON, others as plain text (the premium-only
    block on the Web API is one of those), so both are worth reading.
    """
    message = ""
    try:
        payload = resp.json().get("error", {})
        message = payload.get("message", "") if isinstance(payload, dict) else str(payload)
    except Exception:
        message = ""
    if not message:
        message = (resp.text or "").strip()[:300]
    return f"Spotify says: {message}" if message else f"Spotify replied {resp.status_code}."


def spotify_get(path: str, token: str, params: dict | None = None) -> tuple[dict | None, str]:
    """Returns (data, problem). Exactly one of the two is filled in."""
    try:
        resp = requests.get(
            SPOTIFY_API + path,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
    except Exception as e:
        return None, f"Could not reach Spotify: {e}"

    if resp.status_code >= 400:
        problem = spotify_error(resp)
        print(f"  Spotify GET {path} -> {resp.status_code}: {problem}", flush=True)
        return None, problem
    return resp.json(), ""


def spotify_track_uri(token: str, artist: str, title: str) -> str | None:
    """A field-scoped search first, then a loose one for odd metadata."""
    for query in (f'track:"{title}" artist:"{artist}"', f"{artist} {title}".strip()):
        data, _ = spotify_get("/search", token, {"q": query, "type": "track", "limit": 1})
        items = (data or {}).get("tracks", {}).get("items", [])
        if items:
            return items[0]["uri"]
    return None


def spotify_export(playlist: dict) -> dict:
    token = spotify_access_token()
    if not token:
        return {"error": "Spotify is not connected."}

    profile, problem = spotify_get("/me", token)
    if not profile or not profile.get("id"):
        # Free accounts get a 403 here: Spotify only lets the Web API through
        # for apps whose owner has an active Premium subscription.
        return {"error": problem or "Could not read your Spotify profile. Connect Spotify again."}

    uris, missing = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        found = list(
            pool.map(
                lambda song: (song, spotify_track_uri(token, song.get("artist", ""), song.get("title", ""))),
                playlist["songs"],
            )
        )
    for song, uri in found:
        if uri:
            uris.append(uri)
        else:
            missing.append(f"{song.get('artist', '')} - {song.get('title', '')}".strip(" -"))

    if not uris:
        return {"error": "No song of this playlist could be found on Spotify."}

    try:
        created = requests.post(
            f"{SPOTIFY_API}/users/{profile['id']}/playlists",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": playlist["name"],
                "public": False,
                "description": "Created by SongRadar",
            },
            timeout=20,
        ).json()
    except Exception as e:
        return {"error": f"Could not create the playlist: {e}"}

    playlist_id = created.get("id")
    if not playlist_id:
        detail = created.get("error", {})
        detail = detail.get("message") if isinstance(detail, dict) else str(detail)
        return {"error": f"Spotify says: {detail}" if detail else "Spotify refused to create the playlist."}

    for start in range(0, len(uris), SPOTIFY_TRACKS_PER_REQUEST):
        batch = uris[start:start + SPOTIFY_TRACKS_PER_REQUEST]
        try:
            resp = requests.post(
                f"{SPOTIFY_API}/playlists/{playlist_id}/tracks",
                headers={"Authorization": f"Bearer {token}"},
                json={"uris": batch},
                timeout=20,
            )
            if resp.status_code >= 400:
                return {"error": f"Could not add the songs: {resp.text[:200]}"}
        except Exception as e:
            return {"error": f"Could not add the songs: {e}"}

    return {
        "url": created.get("external_urls", {}).get("spotify", ""),
        "found": len(uris),
        "total": len(playlist["songs"]),
        "missing": missing,
    }


# -- YouTube playlist ---------------------------------------------------------
# youtube.com/watch_videos?video_ids=... builds a throwaway playlist from video
# ids, no account or API key involved.
#
# YouTube keeps only the first 50 of them, measured: send 60, 80 or 117 and the
# list that comes back still reports totalVideos 50. So a longer playlist is
# split into one list per 50 and nothing is dropped.
#
# Playback has no limit at all: the queue travels inside the embed URL, and a
# hundred songs is about 1.4 KB of it.
WATCH_VIDEOS_LIMIT = 50
YOUTUBE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# Looking a song up on YouTube takes a couple of seconds, so a hundred-song
# playlist would stall on every restart. The answers do not change, so they are
# kept on disk.
VIDEO_CACHE_FILE = os.path.join(data_dir(), "videos.json")
_video_id_cache: dict[str, str] = {}
_video_id_lock = threading.Lock()


def load_video_cache():
    global _video_id_cache
    try:
        with open(VIDEO_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        _video_id_cache = {k: v for k, v in data.items() if isinstance(v, str)}
        print(f"  Video ids: {len(_video_id_cache)} cached", flush=True)
    except FileNotFoundError:
        _video_id_cache = {}
    except Exception as e:
        print(f"  Could not read the video cache: {e}", flush=True)
        _video_id_cache = {}


def save_video_cache():
    tmp = VIDEO_CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_video_id_cache, f, ensure_ascii=False, indent=0)
        os.replace(tmp, VIDEO_CACHE_FILE)
    except Exception as e:
        print(f"  Could not save the video cache: {e}", flush=True)


def youtube_video_id(query: str) -> str | None:
    """First video id on the YouTube search page for this query."""
    with _video_id_lock:
        if query in _video_id_cache:
            return _video_id_cache[query]

    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers={"User-Agent": YOUTUBE_UA, "Accept-Language": "en-US,en;q=0.9"},
            cookies={"CONSENT": "YES+cb"},
            timeout=15,
        )
        match = re.search('"videoId":"([A-Za-z0-9_-]{11})"', resp.text)
    except Exception as e:
        print(f"  YouTube search failed for {query!r}: {e}", flush=True)
        return None

    if not match:
        return None

    video_id = match.group(1)
    with _video_id_lock:
        _video_id_cache[query] = video_id
        save_video_cache()
    return video_id


def playlist_songs() -> list[dict]:
    """History oldest first, one entry per song."""
    songs, seen = [], set()
    for song in reversed(song_history):
        key = (song.get("artist", "").lower(), song.get("title", "").lower())
        if key in seen:
            continue
        seen.add(key)
        songs.append(song)
    return songs


def youtube_playlist_page(watch_url: str) -> str:
    """Turn the watch_videos link into the playlist page.

    watch_videos drops you into the player with the list as a queue, which is
    not where YouTube offers to keep it. Following its redirect exposes the
    temporary list id, and the playlist page for that id is the one with the
    save option on it.
    """
    try:
        resp = requests.get(
            watch_url,
            headers={"User-Agent": YOUTUBE_UA, "Accept-Language": "en-US,en;q=0.9"},
            cookies={"CONSENT": "YES+cb"},
            timeout=20,
        )
        match = re.search(r"list=([A-Za-z0-9_-]+)", resp.url)
    except Exception as e:
        print(f"  Could not resolve the YouTube list id: {e}", flush=True)
        return ""
    return f"https://www.youtube.com/playlist?list={match.group(1)}" if match else ""


def resolve_video_ids(queries: list[str]) -> tuple[list[str], list[str]]:
    """Video ids in the order asked for, plus the queries that found nothing."""
    # Each lookup is a search page fetch, so a long playlist is worth widening
    # for: 8 at a time keeps a hundred songs under a handful of seconds.
    with ThreadPoolExecutor(max_workers=8) as pool:
        video_ids = list(pool.map(youtube_video_id, queries))

    found = [v for v in video_ids if v]
    missing = [q for q, v in zip(queries, video_ids) if not v]
    return found, missing


def build_playlist_urls(queries: list[str]) -> tuple[list[str], list[str]]:
    """One YouTube list per 50 songs, because that is all one link can hold."""
    found, missing = resolve_video_ids(queries)

    urls = []
    for start in range(0, len(found), WATCH_VIDEOS_LIMIT):
        chunk = found[start : start + WATCH_VIDEOS_LIMIT]
        watch_url = "https://www.youtube.com/watch_videos?video_ids=" + ",".join(chunk)
        urls.append(youtube_playlist_page(watch_url) or watch_url)
    return urls, missing


def collect_into_active(song: dict) -> bool:
    """File a recognized song into the active playlist, if there is one."""
    with _playlists_lock:
        playlist = find_playlist(active_playlist_id or "")
        if not playlist:
            return False
        added = append_song(playlist, song["title"], song["artist"], song.get("cover", ""))
        if added:
            save_playlists()
    if added:
        print(f"     + added to \"{playlist['name']}\"", flush=True)
    return added


# -- WebSocket broadcast ------------------------------------------------------
def broadcast_song():
    msg = json.dumps(
        {"type": "song", "current": current_song, "history": song_history[:20]},
        ensure_ascii=False,
    )
    if _loop:
        asyncio.run_coroutine_threadsafe(_send_all(msg), _loop)


def broadcast_playlists():
    msg = json.dumps(
        {"type": "playlists", "playlists": playlists, "active": active_playlist_id},
        ensure_ascii=False,
    )
    if _loop:
        asyncio.run_coroutine_threadsafe(_send_all(msg), _loop)


async def _send_all(msg):
    dead = []
    for ws in clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in clients:
            clients.remove(ws)


# -- FastAPI app --------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):
    global _loop, running
    _loop = asyncio.get_event_loop()
    load_playlists()
    load_spotify_config()
    load_youtube_config()
    load_video_cache()
    thread = threading.Thread(target=audio_capture_loop, daemon=True)
    thread.start()
    # The interface lives on the web server, so that is what the browser opens.
    if os.environ.get("SONGRADAR_OPEN_BROWSER", "1") != "0":
        threading.Thread(
            target=lambda: (time.sleep(1), webbrowser.open(WEB_URL)), daemon=True
        ).start()
    yield
    running = False


app = FastAPI(lifespan=lifespan)

# The interface is served from another port, so the browser needs permission to
# talk to this one. Only the local interface origins, nothing else.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{WEB_PORT}",
        f"http://127.0.0.1:{WEB_PORT}",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# The interface is the Next.js app; this only points at it, so hitting the API
# port by hand is not a dead end.
LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SongRadar service</title>
<style>
  body {
    font-family: 'Segoe UI', -apple-system, sans-serif; background: #060d14; color: #e2f1f5;
    height: 100vh; margin: 0; display: flex; align-items: center; justify-content: center; text-align: center;
  }
  .box { max-width: 420px; padding: 40px; }
  h1 { font-size: 1.4rem; margin: 0 0 10px; letter-spacing: -0.02em; }
  p { color: #7c98a6; font-size: 0.92rem; line-height: 1.7; margin: 0 0 18px; }
  a { color: #2dd4bf; text-decoration: none; font-weight: 600; }
  a:hover { text-decoration: underline; }
  code { background: rgba(255,255,255,0.06); padding: 2px 7px; border-radius: 5px; font-size: 0.82rem; }
</style>
</head>
<body>
  <div class="box">
    <h1>SongRadar service</h1>
    <p>This port is the recognition API. The interface runs on its own server.</p>
    <p><a href="__WEB_URL__">__WEB_URL__</a></p>
    <p>If that page does not load, start it with <code>npm start</code> inside <code>web/</code>, or use <code>start.bat</code>, which launches both.</p>
  </div>
</body>
</html>"""


if not BUNDLED_WEB:

    @app.get("/")
    async def get_page():
        return HTMLResponse(LANDING_PAGE.replace("__WEB_URL__", WEB_URL))


@app.get("/video")
async def get_video(artist: str = "", title: str = ""):
    """The YouTube video id for one song, so the page can embed it."""
    if not title.strip():
        return {"error": "A song title is required."}
    query = f"{artist} {title}".strip()
    video_id = await asyncio.to_thread(youtube_video_id, query)
    if not video_id:
        return {"error": "No video found for this song."}
    return {"id": video_id}


@app.get("/history.txt")
async def history_text():
    lines = [
        f"{i}. {s.get('artist', '')} - {s.get('title', '')}  [{s.get('time', '')}]"
        for i, s in enumerate(reversed(song_history), 1)
    ]
    return PlainTextResponse("\n".join(lines))


@app.post("/youtube-playlist")
async def youtube_playlist():
    songs = playlist_songs()
    if not songs:
        return {"error": "No songs recognized yet."}

    queries = [f"{s.get('artist', '')} {s.get('title', '')}".strip() for s in songs]
    urls, missing = await asyncio.to_thread(build_playlist_urls, queries)
    if not urls:
        return {"error": "No song could be found on YouTube."}

    return {
        "urls": urls,
        "found": len(queries) - len(missing),
        "total": len(queries),
        "missing": missing,
    }


SPOTIFY_CALLBACK_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SongRadar and Spotify</title>
<style>
  body {
    font-family: 'Segoe UI', -apple-system, sans-serif; background: #0a0a0f; color: #ddd;
    height: 100vh; margin: 0; display: flex; align-items: center; justify-content: center;
  }
  .box { text-align: center; padding: 40px; max-width: 420px; }
  h1 { font-size: 1.3rem; margin: 0 0 12px; color: __COLOR__; }
  p { color: #888; font-size: 0.95rem; line-height: 1.6; margin: 0; }
</style>
</head>
<body>
  <div class="box">
    <h1>__TITLE__</h1>
    <p>__MESSAGE__</p>
  </div>
</body>
</html>"""


# -- YouTube account endpoints ------------------------------------------------
@app.get("/youtube/status")
async def youtube_status():
    return {
        "configured": bool(youtube_config.get("client_id") and youtube_config.get("client_secret")),
        "connected": bool(youtube_config.get("refresh_token")),
        "channel": youtube_config.get("channel", ""),
        "redirect_uri": YOUTUBE_REDIRECT_URI,
    }


@app.post("/youtube/config")
async def set_youtube_config(payload: dict = Body(...)):
    client_id = str(payload.get("client_id", "")).strip()
    client_secret = str(payload.get("client_secret", "")).strip()
    if not client_id or not client_secret:
        return {"error": "Google needs both the client id and the client secret."}

    youtube_config["client_id"] = client_id
    youtube_config["client_secret"] = client_secret
    # Different credentials mean the old authorization is worthless.
    youtube_config.pop("refresh_token", None)
    youtube_config.pop("channel", None)
    _youtube_token["access_token"] = ""
    save_youtube_config()
    return {"configured": True, "connected": False}


@app.post("/youtube/disconnect")
async def youtube_disconnect():
    youtube_config.pop("refresh_token", None)
    youtube_config.pop("channel", None)
    _youtube_token["access_token"] = ""
    _youtube_token["expires_at"] = 0.0
    save_youtube_config()
    return {"connected": False}


@app.delete("/youtube/config")
async def forget_youtube_config():
    """Forget the credentials entirely, not just the authorization."""
    youtube_config.clear()
    _youtube_token["access_token"] = ""
    _youtube_token["expires_at"] = 0.0
    try:
        os.remove(YOUTUBE_CONFIG_FILE)
    except OSError:
        pass
    return {"configured": False, "connected": False}


@app.get("/youtube/login")
async def youtube_login():
    url = youtube_login_url()
    if not url:
        return {"error": "Set your Google client id and secret first."}
    return RedirectResponse(url)


def google_denied_reason(error: str) -> str:
    """Google's error codes are short. These are the ones people actually hit."""
    if error == "access_denied":
        return (
            "Google blocked the sign-in. While the project is in Testing, only "
            "accounts listed as test users may sign in: open the Google Cloud "
            "console, go to APIs and Services, OAuth consent screen, Audience, "
            "and add your own Google address under Test users. Then press "
            "Connect YouTube again. Publishing the project does the same and "
            "also stops the authorization expiring every 7 days."
        )
    if error == "redirect_uri_mismatch":
        return (
            "The redirect URI registered in Google Cloud does not match the one "
            "SongRadar uses. It has to be exactly "
            f"{YOUTUBE_REDIRECT_URI}"
        )
    return error


@app.get("/youtube/callback")
async def youtube_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(
            callback_page("YouTube was not connected", google_denied_reason(error), ok=False)
        )
    if not code or not state:
        return HTMLResponse(
            callback_page("YouTube was not connected", "The callback was incomplete.", ok=False)
        )

    problem = await asyncio.to_thread(youtube_exchange_code, code, state)
    if problem:
        return HTMLResponse(callback_page("YouTube was not connected", problem, ok=False))

    channel = youtube_config.get("channel", "")
    return HTMLResponse(
        callback_page(
            "YouTube connected",
            f"Signed in as {channel}. You can close this tab and go back to SongRadar."
            if channel
            else "You can close this tab and go back to SongRadar.",
            ok=True,
        )
    )


@app.post("/playlists/{playlist_id}/youtube-save")
async def playlist_youtube_save(playlist_id: str):
    """Create the playlist on the account, for keeps."""
    playlist = find_playlist(playlist_id)
    if not playlist:
        return {"error": "Playlist not found."}
    if not playlist["songs"]:
        return {"error": "This playlist is empty."}
    if not youtube_config.get("client_id"):
        return {"error": "Set your Google client id and secret first."}
    if not youtube_config.get("refresh_token"):
        return {"error": "Connect YouTube first."}

    return await asyncio.to_thread(youtube_save_playlist, playlist)


# -- Spotify endpoints --------------------------------------------------------
@app.get("/spotify/status")
async def spotify_status():
    return {
        "configured": bool(spotify_config.get("client_id")),
        "connected": bool(spotify_config.get("refresh_token")),
        "user": spotify_config.get("user", ""),
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }


@app.post("/spotify/config")
async def set_spotify_config(payload: dict = Body(...)):
    client_id = str(payload.get("client_id", "")).strip()
    if not client_id:
        return {"error": "A client id is required."}

    spotify_config["client_id"] = client_id
    # A different app means the old authorization is worthless.
    spotify_config.pop("refresh_token", None)
    spotify_config.pop("user", None)
    _spotify_token["access_token"] = ""
    save_spotify_config()
    return {"configured": True, "connected": False}


@app.post("/spotify/disconnect")
async def spotify_disconnect():
    spotify_config.pop("refresh_token", None)
    spotify_config.pop("user", None)
    _spotify_token["access_token"] = ""
    _spotify_token["expires_at"] = 0.0
    save_spotify_config()
    return {"connected": False}


@app.delete("/spotify/config")
async def forget_spotify_config():
    """Forget the credentials entirely, not just the authorization."""
    spotify_config.clear()
    _spotify_token["access_token"] = ""
    _spotify_token["expires_at"] = 0.0
    try:
        os.remove(SPOTIFY_CONFIG_FILE)
    except OSError:
        pass
    return {"configured": False, "connected": False}


@app.get("/spotify/login")
async def spotify_login():
    url = spotify_login_url()
    if not url:
        return {"error": "Set your Spotify client id first."}
    return RedirectResponse(url)


@app.get("/spotify/callback")
async def spotify_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(callback_page("Spotify was not connected", error, ok=False))

    if not code or not state:
        return HTMLResponse(callback_page("Spotify was not connected", "The callback was incomplete.", ok=False))

    problem = await asyncio.to_thread(spotify_exchange_code, code, state)
    if problem:
        return HTMLResponse(callback_page("Spotify was not connected", problem, ok=False))

    who = spotify_config.get("user", "")
    return HTMLResponse(
        callback_page(
            "Spotify connected",
            f"Signed in as {who}. You can close this tab and go back to SongRadar."
            if who
            else "You can close this tab and go back to SongRadar.",
            ok=True,
        )
    )


def callback_page(title: str, message: str, ok: bool) -> str:  # noqa: E302
    return (
        SPOTIFY_CALLBACK_PAGE.replace("__TITLE__", title)
        .replace("__MESSAGE__", message)
        .replace("__COLOR__", "#1db954" if ok else "#ef4444")
    )


@app.post("/playlists/{playlist_id}/spotify")
async def playlist_to_spotify(playlist_id: str):
    playlist = find_playlist(playlist_id)
    if not playlist:
        return {"error": "Playlist not found."}
    if not playlist["songs"]:
        return {"error": "This playlist is empty."}
    if not spotify_config.get("client_id"):
        return {"error": "Set your Spotify client id first."}
    if not spotify_config.get("refresh_token"):
        return {"error": "Connect Spotify first."}

    return await asyncio.to_thread(spotify_export, playlist)


# -- Playlist endpoints -------------------------------------------------------
@app.get("/status")
async def status():
    """What the service is doing, for when something looks wrong."""
    return {
        "listening": capture_sources,
        "collecting": (find_playlist(active_playlist_id or "") or {}).get("name", ""),
        "recognized": len(song_history),
        "current": current_song.get("title", ""),
        "window_seconds": WINDOW_SECONDS,
        "packaged": FROZEN,
    }


@app.get("/playlists")
async def get_playlists():
    return {"playlists": playlists, "active": active_playlist_id}


@app.post("/active")
async def set_active(payload: dict = Body(...)):
    """Point recognition at a playlist, or at nothing when id is empty."""
    global active_playlist_id

    playlist_id = str(payload.get("playlist_id", "")).strip()
    if not playlist_id:
        active_playlist_id = None
    else:
        if not find_playlist(playlist_id):
            return {"error": "Playlist not found."}
        active_playlist_id = playlist_id

    with _playlists_lock:
        save_playlists()
    broadcast_playlists()
    return {"active": active_playlist_id}


@app.post("/playlists")
async def create_playlist(payload: dict = Body(...)):
    name = str(payload.get("name", "")).strip() or "Untitled playlist"
    playlist = {
        "id": new_id(),
        "name": name[:80],
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "songs": [],
    }
    global active_playlist_id
    with _playlists_lock:
        playlists.append(playlist)
        if payload.get("activate"):
            active_playlist_id = playlist["id"]
        save_playlists()
    broadcast_playlists()
    return {"playlist": playlist, "active": active_playlist_id}


@app.patch("/playlists/{playlist_id}")
async def rename_playlist(playlist_id: str, payload: dict = Body(...)):
    name = str(payload.get("name", "")).strip()
    if not name:
        return {"error": "A name is required."}
    with _playlists_lock:
        playlist = find_playlist(playlist_id)
        if not playlist:
            return {"error": "Playlist not found."}
        playlist["name"] = name[:80]
        save_playlists()
    broadcast_playlists()
    return {"playlist": playlist}


@app.delete("/playlists/{playlist_id}")
async def delete_playlist(playlist_id: str):
    with _playlists_lock:
        playlist = find_playlist(playlist_id)
        if not playlist:
            return {"error": "Playlist not found."}
        playlists.remove(playlist)
        global active_playlist_id
        if active_playlist_id == playlist_id:
            active_playlist_id = None
        save_playlists()
    broadcast_playlists()
    return {"deleted": playlist_id, "active": active_playlist_id}


@app.post("/playlists/{playlist_id}/songs")
async def add_song(playlist_id: str, payload: dict = Body(...)):
    title = str(payload.get("title", "")).strip()
    artist = str(payload.get("artist", "")).strip()
    if not title:
        return {"error": "A song title is required."}

    with _playlists_lock:
        playlist = find_playlist(playlist_id)
        if not playlist:
            return {"error": "Playlist not found."}

        if not append_song(playlist, title, artist, str(payload.get("cover", ""))):
            return {"added": False, "reason": "already in this playlist", "playlist": playlist}
        save_playlists()
    broadcast_playlists()
    return {"added": True, "playlist": playlist}


@app.delete("/playlists/{playlist_id}/songs/{song_id}")
async def remove_song(playlist_id: str, song_id: str):
    with _playlists_lock:
        playlist = find_playlist(playlist_id)
        if not playlist:
            return {"error": "Playlist not found."}
        song = next((s for s in playlist["songs"] if s["id"] == song_id), None)
        if not song:
            return {"error": "Song not found."}
        playlist["songs"].remove(song)
        save_playlists()
    broadcast_playlists()
    return {"removed": song_id}


@app.get("/playlists/{playlist_id}/text")
async def playlist_text(playlist_id: str):
    playlist = find_playlist(playlist_id)
    if not playlist:
        return PlainTextResponse("", status_code=404)
    lines = [f"{playlist['name']}", ""]
    lines += [
        f"{i}. {s['artist']} - {s['title']}"
        for i, s in enumerate(playlist["songs"], 1)
    ]
    return PlainTextResponse("\n".join(lines))


@app.post("/playlists/{playlist_id}/videos")
async def playlist_videos(playlist_id: str):
    """Every video id of a playlist, in order, so the page can queue them up."""
    playlist = find_playlist(playlist_id)
    if not playlist:
        return {"error": "Playlist not found."}
    if not playlist["songs"]:
        return {"error": "This playlist is empty."}

    songs = playlist["songs"]
    queries = [f"{s['artist']} {s['title']}".strip() for s in songs]
    ids, missing = await asyncio.to_thread(resolve_video_ids, queries)
    if not ids:
        return {"error": "No song of this playlist could be found on YouTube."}

    # Paired with the song they belong to: the page highlights the row that is
    # playing, and a song with no video simply is not in the queue.
    found = iter(ids)
    queue = []
    for song, query in zip(songs, queries):
        if query in missing:
            continue
        queue.append({"song_id": song["id"], "video_id": next(found), "title": song["title"], "artist": song["artist"]})

    return {
        "queue": queue,
        "found": len(queue),
        "total": len(queries),
        "missing": missing,
    }


@app.post("/playlists/{playlist_id}/youtube")
async def playlist_youtube(playlist_id: str):
    playlist = find_playlist(playlist_id)
    if not playlist:
        return {"error": "Playlist not found."}
    songs = playlist["songs"]
    if not songs:
        return {"error": "This playlist is empty."}

    queries = [f"{s['artist']} {s['title']}".strip() for s in songs]
    urls, missing = await asyncio.to_thread(build_playlist_urls, queries)
    if not urls:
        return {"error": "No song could be found on YouTube."}
    return {
        "urls": urls,
        "found": len(queries) - len(missing),
        "total": len(queries),
        "missing": missing,
    }


@app.delete("/history/{song_id}")
async def delete_from_history(song_id: str):
    song = next((s for s in song_history if s.get("id") == song_id), None)
    if not song:
        return {"error": "Song not found."}
    song_history.remove(song)
    broadcast_song()
    return {"removed": song_id}


# Mounted last, so every API route above wins over the static files.
if BUNDLED_WEB:

    @app.get("/")
    async def index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    await websocket.send_text(
        json.dumps(
            {"type": "playlists", "playlists": playlists, "active": active_playlist_id},
            ensure_ascii=False,
        )
    )
    if current_song.get("title"):
        await websocket.send_text(
            json.dumps(
                {"type": "song", "current": current_song, "history": song_history[:20]},
                ensure_ascii=False,
            )
        )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in clients:
            clients.remove(websocket)


if BUNDLED_WEB:
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    print(flush=True)
    print("  === SongRadar ===", flush=True)
    if BUNDLED_WEB:
        print(f"  Open:  {WEB_URL}", flush=True)
    else:
        print(f"  API:       http://127.0.0.1:{PORT}", flush=True)
        print(f"  Interface: {WEB_URL}", flush=True)
    print("  Close this window to stop it.", flush=True)
    print(flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
