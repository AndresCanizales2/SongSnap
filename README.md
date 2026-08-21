# SongRadar 📡

**Recognizes the music playing around you or on your PC, and turns it into playlists you can play, copy, or push to YouTube and Spotify.**

SongRadar listens through your microphone *and* to your computer's own audio, identifies each song by its audio fingerprint, and files it into the playlist you are collecting into. You can play any song — or the whole playlist — in a YouTube player built into the page.

---

## Install

### The easy way

1. Download **`SongRadar.exe`** from the [releases](../../releases).
2. Double-click it.
3. Your browser opens at `http://127.0.0.1:8000`. Name a playlist and play music.

That single file carries Python, the audio capture and the whole interface. **Nothing else to install.** It keeps your playlists in a `playlists.json` next to itself.

Windows SmartScreen will warn you the first time, because the file is not code-signed: *More info → Run anyway*.

To stop SongRadar, close its console window. Nothing in the web page can stop it.

### From source

Needed:

| | |
|---|---|
| **Windows 10 / 11** | WASAPI loopback, used to capture the PC's own audio, is Windows-only |
| **Python 3.10 – 3.12** | not 3.13+: `pydub` needs `audioop`, removed in 3.13, and `pyaudiowpatch` has no 3.14 wheels |
| **Node.js 20+** | only to build the interface |
| **Git** | the recognition library is installed from its repo, not from PyPI |

```bash
git clone https://github.com/AndresCanizales2/SongRadar.git
cd SongRadar
start.bat
```

`start.bat` creates the virtual environment, installs the dependencies, builds the interface the first time, and starts everything on `http://127.0.0.1:8000`.

> **Where your playlists live.** Running from source keeps them in this folder. The packaged `SongRadar.exe` keeps them next to the exe instead, so it stays portable. `start.bat` always runs from source, even if you have built an exe, so your playlists do not change under you depending on how you started it. To move them, copy `playlists.json` across.

### Building the .exe yourself

```bash
python build.py
```

It exports the interface with Next.js and bundles it with PyInstaller into `dist/SongRadar.exe` (~27 MB). `python build.py --web` rebuilds only the interface.

---

## How it works

```
        Microphone                    PC audio output
             │                              │
             ▼                              ▼
      default input                  WASAPI loopback
             │                              │
             ▼  rolling 8s window           ▼  rolling 8s window
    ┌────────────────┐                      │
    │ 1. try the mic │                      │
    └────────┬───────┘                      │
             │ no match                     │
             ▼                              ▼
                      ┌────────────────────────┐
                      │ 2. try the PC's audio  │
                      └───────────┬────────────┘
                                  │
                                  ▼
                    audio fingerprint (frequency peaks)
                                  │
                                  ▼
                          Shazam recognition
                                  │
                                  ▼
                    the playlist you are collecting into
```

1. **Two sources, never mixed.** Mixing blurs both fingerprints and matches neither, so the microphone is fingerprinted on its own first, and the PC's audio only if the mic found nothing.
2. **8 second windows**, overlapping, taken every 5 seconds. Eight is what one Shazam signature holds, so each attempt carries as much evidence as the format allows.
3. **Quiet input is lifted** towards full scale before fingerprinting, and a silent source is skipped entirely.
4. **The match is filed** into the active playlist, without duplicates, and saved to disk immediately.

---

## Using it

### The screens

| Screen | What it is for |
|---|---|
| **Start** | Name the playlist you are starting. Everything recognized from then on goes into it. Your existing playlists are right there, filtered as you type, so you can carry on with one instead of making a near-duplicate. |
| **Listening** | What is playing now, and the playlist filling up underneath. |
| **My playlists** | Every playlist as a card, with the one being filled marked *collecting*. |
| **One playlist** | Its full contents, with the player and the export buttons on top. |

### Playing

**▶ Play all** at the top of a playlist plays every song in order in an embedded YouTube player. The ▶ on a single song starts the player there and **keeps going with the rest of the list**.

**There is no limit on how many songs play.** The queue travels inside the embed URL — a hundred songs is about 1.4 KB of it — so the whole playlist goes in, however long it grows.

Each song's video is looked up once and kept in `videos.json`, and SongRadar resolves it in the background the moment it recognizes the song. Pressing play on a long playlist is then instant: a 117-song list queues in 0.02s.

The **export** to YouTube is the one place a limit exists, and it is YouTube's, not SongRadar's: one `watch_videos` link holds exactly 50 songs. Measured, not assumed — send 60, 80 or 117 ids and the list that comes back still reports `totalVideos: 50`, dropping the rest without a word. So a longer playlist is exported as **several lists of 50**, each opening in its own tab, and nothing is left behind.

The player sits above the list, shows `3/12` and the song's name, and highlights the row that is playing. Only one player exists in the page.

### Everything else

| Action | Where |
|---|---|
| Rename a playlist | Double-click its name, anywhere it appears |
| Add the song playing now to a playlist | **Add to playlist**, next to its name |
| Remove a song | the **×** on its row |
| Copy a playlist as text | **Copy** |
| Send it to YouTube | **YouTube** — a temporary list, or a real saved playlist once an account is connected |
| Send it to Spotify | **Spotify** (see below) |
| Stop filling a playlist | **Stop collecting** |

### Audio sources

Both are used by default. To use only one:

```bash
set SONGRADAR_SOURCES=system   # PC audio only
set SONGRADAR_SOURCES=mic      # microphone only
```

> If your microphone hears your speakers, the mic attempt already matches whatever the PC plays, just through a worse channel. `SONGRADAR_SOURCES=system` skips to the clean source and halves the time per cycle.

---

## Connecting a YouTube account

Without this, the **YouTube** button opens throwaway lists that YouTube usually will not let you keep. Connect an account and the same button creates the playlist **for real**, private, on your channel.

It is free and needs no Premium — only a Google Cloud project, once:

1. Press the **⚙** next to the YouTube button.
2. Create a project in [Google Cloud](https://console.cloud.google.com/projectcreate).
3. Enable [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
4. On the OAuth consent screen choose **External** and add your own Google address as a **test user**.
5. Create an **OAuth client ID** of type **Web application** with this redirect URI: `http://127.0.0.1:8000/youtube/callback`
6. Paste the **Client ID** and **Client secret** into SongRadar, press **Save**, then **Connect YouTube**.

Google asks for a client secret even with PKCE, unlike Spotify. Both halves are stored in `youtube.json` beside the app and never leave the machine — treat that file like a password. **Disconnect** removes the authorization.

Two things Google does that are worth knowing before you start:

| | |
|---|---|
| **"This app isn't verified"** | Expected: it is your own app, used by you. Choose **Advanced → Go to SongRadar**. Verification is only needed to publish an app to strangers. |
| **The authorization expires after 7 days** | While the project is in *Testing*, Google expires refresh tokens weekly. SongRadar then says so and you press **Connect YouTube** again. Publishing the project (still unverified) stops the expiry. |

**Quota.** A project gets 10,000 units a day, and each song inserted costs 50, so about **195 songs a day**. Saving a 117-song playlist uses most of it. When it runs out SongRadar says so, names the quota, and tells you it resets at midnight Pacific time.

---

## Spotify

> **Spotify Premium is required**, on the account that owns the app. Spotify blocks the Web API for development-mode apps whose owner is on a free account, refusing every call — even reading your own profile — with `403 Active premium subscription required for the owner of the app`. There is no way around it from this side; without Premium, use the **YouTube** button, which needs no account at all.

Setup, once:

1. Click **Spotify** in the playlists header.
2. Create an app at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard).
3. Add exactly this redirect URI: `http://127.0.0.1:8000/spotify/callback`
4. Tick **Web API**, save, copy the **Client ID**.
5. Paste it into SongRadar, press **Save**, then **Connect Spotify** and authorize.

SongRadar uses the Authorization Code flow with **PKCE**: you log in on Spotify's own page, SongRadar never sees your password, and there is no client secret anywhere. The client id and refresh token live in `spotify.json` next to the app — treat that file like a password. **Disconnect** deletes it.

---

## Troubleshooting

**Nothing is being recognized.** Open `http://127.0.0.1:8000/status`. `listening` should name your sources:

```json
{ "listening": ["Microphone", "System audio"], "collecting": "Friday night" }
```

If it is empty, no capture device was found. If `collecting` is empty, nothing is being filed — pick a playlist and press **Listen into it**.

**Recognition is slow.** Each attempt costs about 4.5 seconds: the fingerprint is computed in pure Python (~0.5s per second of audio) plus roughly 1.2s of network. With both sources and no match a cycle takes about 9 seconds. `SONGRADAR_SOURCES=system` halves it.

**A song never matches.** Fingerprinting needs the recording it knows. Covers, live versions, remixes and self-released tracks often are not in the database. The window is skipped and the next one is tried.

**The playlist will not save on YouTube.** These are temporary, unlisted lists. YouTube decides whether it offers to keep one, and lately often does not. A permanent playlist would need the YouTube Data API behind a Google OAuth app, which SongRadar does not use.

**YouTube opened several tabs.** That is a playlist of more than 50 songs: one link cannot hold more, so it is split. Playback is not split — that plays the whole list in one go.

**Port 8000 is taken.** `set SONGRADAR_PORT=8010` before starting. Note the Spotify redirect URI is tied to 8000, so change it in the Spotify dashboard too if you use Spotify.

---

## What it can and cannot recognize

| | |
|---|---|
| Mainstream music, any language | works well |
| Anime openings, endings | works well |
| Instrumentals | works — fingerprinting does not need lyrics |
| Covers, live versions, remixes | usually not: a different recording is a different fingerprint |
| Self-released or upload-only tracks | usually not in the database |

---

## Project layout

```
SongRadar/
├── app.py            # the service: audio capture, recognition, playlists, exports
├── build.py          # exports the interface and bundles the exe
├── start.bat         # runs it from source
├── requirements.txt  # Python dependencies
├── web/              # Next.js interface
│   ├── app/          # start, listening, playlists, one playlist
│   ├── components/   # player, rows, editable names, Spotify panel
│   └── lib/          # api calls, shared state, YouTube player API
├── playlists.json    # your playlists (created on first use, not in git)
└── spotify.json      # Spotify credentials (created on setup, not in git)
```

---

## Built with

| Piece | What |
|---|---|
| Service | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| Interface | [Next.js](https://nextjs.org/) 16 + React 19, exported as static files |
| Audio capture | [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) (WASAPI loopback) |
| Recognition | [ShazamAPI](https://github.com/Numenorean/ShazamAPI) — unofficial, reverse-engineered |
| Playback and YouTube playlists | YouTube embed + public search page |
| Spotify playlists | [Spotify Web API](https://developer.spotify.com/documentation/web-api) (official, OAuth with PKCE) |
| Packaging | [PyInstaller](https://pyinstaller.org/) |

---

## Privacy

Your audio never leaves the machine. What is sent for recognition is a *fingerprint* — the loudest frequency peaks of an 8 second window — not the sound itself. Playlists and credentials are files on your disk; there is no server behind SongRadar.

---

## Disclaimer

This project uses [ShazamAPI](https://github.com/Numenorean/ShazamAPI), an **unofficial, reverse-engineered** library not affiliated with or endorsed by Shazam Entertainment Ltd. or Apple Inc. YouTube video ids are read from the public search page. Neither is a supported interface, so either can break without warning.

SongRadar is an independent, source-available project for **personal, noncommercial use**. All song metadata and recognition results come from third-party services.

---

## License

[**PolyForm Noncommercial 1.0.0**](https://polyformproject.org/licenses/noncommercial/1.0.0) — see [LICENSE](LICENSE).

Read it, run it, change it, share it, fork it: all fine, for **any noncommercial purpose**. Personal use, study, research, and use inside a nonprofit or an educational institution are all covered explicitly.

What is not allowed is commercial use — selling it, bundling it into a product, or running it as part of a business.

> This is a **source-available** license, not an OSI open source one, so GitHub will show it as "unrecognized" and it is not compatible with open-source-only policies. That is the trade-off of the noncommercial condition.
