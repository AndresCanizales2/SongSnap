"""Builds SongRadar into a single Windows executable.

Steps: export the interface with Next, flatten the navigation payloads so a
plain static server can find them, then bundle everything with PyInstaller.

    python build.py            full build
    python build.py --web      only rebuild the interface
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
OUT = os.path.join(WEB, "out")
DIST = os.path.join(ROOT, "dist")


def run(command, cwd=None):
    print(f"\n> {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, shell=os.name == "nt")
    if result.returncode != 0:
        sys.exit(f"failed: {' '.join(command)}")


def build_web():
    if not os.path.isdir(os.path.join(WEB, "node_modules")):
        run(["npm", "install"], cwd=WEB)
    run(["npm", "run", "build"], cwd=WEB)
    flatten_payloads()


def flatten_payloads():
    """Next exports `x/__next.x/__PAGE__.txt` but asks for `x/__next.x.__PAGE__.txt`.

    Without the flat copy every navigation misses its payload and the browser
    falls back to a full page load, which drops the websocket and stops
    whatever is playing. Copying costs a few kilobytes and keeps navigation
    client-side.
    """
    copied = 0
    for folder, dirs, files in os.walk(OUT):
        for name in files:
            if name != "__PAGE__.txt":
                continue
            parent = os.path.basename(folder)
            if not parent.startswith("__next."):
                continue
            flat = os.path.join(os.path.dirname(folder), f"{parent}.__PAGE__.txt")
            shutil.copyfile(os.path.join(folder, name), flat)
            copied += 1
    print(f"  flattened {copied} navigation payloads")


def build_exe():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    if os.path.isdir(DIST):
        shutil.rmtree(DIST, ignore_errors=True)

    run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--name", "SongRadar",
        "--add-data", f"{OUT}{os.pathsep}web/out",
        "--collect-all", "pyaudiowpatch",
        "--collect-all", "ShazamAPI",
        "--hidden-import", "websockets",
        "--hidden-import", "uvicorn.protocols.websockets.websockets_impl",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "uvicorn.loops.asyncio",
        os.path.join(ROOT, "app.py"),
    ])

    exe = os.path.join(DIST, "SongRadar.exe")
    print(f"\nBuilt: {exe}")
    print(f"Size:  {os.path.getsize(exe) / 1_000_000:.0f} MB")
    print("\nThat single file is the whole app. It writes playlists.json and")
    print("spotify.json next to itself the first time you use them.")


if __name__ == "__main__":
    build_web()
    if "--web" not in sys.argv:
        build_exe()
