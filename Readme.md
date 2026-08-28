# Video Converter

A free, offline desktop app to convert videos between formats, or extract
audio to MP3 — with user-selectable resolution, codec, quality, and bitrate.

No paid services, API keys, or internet connection required. All conversion
is done locally using **FFmpeg**.

## Features

- **Video → Video**: one unified settings panel, defaulting to a common
  broadcast/OTT delivery spec — but every field is independently
  changeable, nothing is locked together:
  - Output format: mp4, mkv, mov, webm, avi (default: mp4)
  - Video codec: synced to format — H.264, H.265, VP9, MPEG4 (default: H.264)
  - Resolution: Original, 4K, 1080p, 720p, 480p, 360p (default: 1080p)
  - Frame rate: native, 24, 25, or 29.97 fps (default: native)
  - Color space: Rec.709/SDR (8-bit) or Rec.2020/HDR (10-bit) (default: Rec.709)
  - Bitrate: 1–100 Mbps slider, hard ceiling via `-maxrate`/`-bufsize` (default: 20 Mbps)
  - Audio: options adapt to the chosen format — e.g. WebM only offers Opus,
    since it can't carry PCM (default: 16-bit PCM @ 48kHz where supported)
  - Output is always forced progressive (no interlacing), regardless of source
- **Video → Audio**: extracts audio to FLAC, WAV, or MP3, with defaults set
  to a common "Preferred / Ideal" speech-data spec (e.g. for dataset/data-
  licensing delivery):
  - Format: FLAC or WAV (lossless), or MP3 as a compressed fallback
  - Bit depth: 24-bit by default (16-bit minimum-acceptable also available)
  - Sample rate: 48kHz by default — dropdown covers 8kHz (telephony-minimum)
    up to 48kHz, so you can match either the "Minimum" or "Preferred" column
    of a spec
  - Channels: Stereo by default (Mono also available)
  - Choosing MP3 swaps the bit-depth control for a bitrate control, since
    bit depth isn't meaningful for a compressed format
- Live progress bar and log output while converting.
- Runs conversion on a background thread — the UI never freezes.

## Requirements

> Running from source needs Python. If you just want a double-click app on
> Windows with no installs, see [Packaging as a standalone
> executable](#packaging-as-a-standalone-executable-no-python-needed-to-run-it) below.

1. **Python 3.9+**
2. **FFmpeg** installed and available on your system PATH.
   - Windows: download a build from https://www.gyan.dev/ffmpeg/builds/,
     unzip it, and add the `bin` folder to your PATH environment variable.
   - macOS: `brew install ffmpeg`
   - Linux (Debian/Ubuntu): `sudo apt install ffmpeg`

   Verify it worked by running `ffmpeg -version` in a terminal.

## Setup

```bash
pip install -r requirements.txt
python main.py
```

## Project structure

```
video_converter/
├── main.py         # entry point — run this
├── gui.py          # CustomTkinter UI (all screens/widgets/threading)
├── converter.py    # FFmpeg command building + execution (no UI code)
└── requirements.txt
```

`converter.py` is UI-independent — you can import it and call its functions
directly from a script or a different interface if you ever want to.

## Notes on quality settings

Instead of asking you to guess a bitrate, video conversion uses FFmpeg's
CRF (Constant Rate Factor) scale, mapped to friendly presets:

| Preset      | CRF |
|-------------|-----|
| Low         | 32  |
| Medium      | 26  |
| High        | 20  |
| Very High   | 16  |

Lower CRF = better quality and bigger file. Medium is a good default for
most use cases.

## A note on the merged delivery-spec defaults

- **PCM audio in MP4**: some older/strict players expect PCM audio in a
  `.mov` container rather than `.mp4`. If your delivery target rejects
  PCM-in-MP4, just switch output format to `mov` — audio options update
  automatically.
- **HDR (Rec.2020)** output uses `yuv420p10le` (10-bit) — this is required
  for HDR; 8-bit HDR isn't standards-compliant, so this isn't user-adjustable
  in that mode.
- **"Progressive only"** is guaranteed by a `bwdif` deinterlace filter that
  only acts on frames actually flagged as interlaced, so progressive sources
  pass through unmodified while interlaced sources get properly deinterlaced.
- **AVI color tags**: the AVI container doesn't preserve color-space
  metadata (a limitation of the format itself, not this tool) — use mp4/mkv/mov
  if the color space tag needs to survive in the file.

## Packaging as a standalone executable (no Python needed to run it)

`converter.py` looks for `ffmpeg`/`ffprobe` next to the app itself (or in an
`ffmpeg/bin` subfolder) before falling back to PATH — so a packaged build
plus a copy of the FFmpeg binaries needs zero installs on the target machine.

### Option A: download a prebuilt copy from GitHub Actions (easiest)

Every push to `main` builds both Windows and macOS versions automatically:

1. Go to the repo's **Actions** tab → open the latest **Build executables** run.
2. Wait for the green check.
3. Scroll to **Artifacts** and download:
   - `VideoConverter-windows` for Windows
   - `VideoConverter-macos` for macOS
4. Unzip it — FFmpeg is already bundled inside, next to the app.
5. **Windows**: double-click `VideoConverter.exe` and run.
6. **macOS**: Gatekeeper will block an unsigned app on first run — right-click
   `VideoConverter` → **Open** → **Open** again to confirm, instead of
   double-clicking. After that it opens normally.

### Option B: build it yourself

**Windows** — run on an actual Windows machine (PyInstaller doesn't
cross-compile):

```bat
build_windows.bat
```

This installs PyInstaller and builds `dist\VideoConverter.exe`. Then drop
`ffmpeg.exe` and `ffprobe.exe` (from https://www.gyan.dev/ffmpeg/builds/,
"essentials" build, `bin` folder) into `dist\` next to it. Zip the folder —
that's the whole distributable, no Python or PATH setup required on the
receiving machine.

**macOS** — run on an actual Mac (same cross-compile limitation):

```bash
pip install -r requirements-dev.txt
pyinstaller --onefile --windowed --name VideoConverter main.py
brew install ffmpeg
cp "$(command -v ffmpeg)" dist/
cp "$(command -v ffprobe)" dist/
```

Note: Homebrew's `ffmpeg`/`ffprobe` are dynamically linked against Homebrew's
libraries — this only works standalone on another Mac that also has Homebrew
installed. For a fully portable build, download a self-contained static
build (e.g. from https://evermeet.cx/ffmpeg/) instead of the `brew install`
copy.

## Extending it further

Ideas if you want to build on this:
- Batch conversion (loop over multiple selected files)
- Drag-and-drop file support (`tkinterdnd2` package)
- Trim start/end time before converting
- A "Cancel" button (terminate the subprocess mid-run)
- Preview thumbnail of the selected video