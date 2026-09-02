"""
converter.py
------------
Core conversion engine. Wraps FFmpeg via subprocess.

This module has NO GUI code in it on purpose — it can be tested or reused
from the command line, a script, or a different UI later.
"""

import subprocess
import shlex
import shutil
import json
import re
import os
import sys


class FFmpegNotFoundError(Exception):
    pass


def _app_dir():
    """Directory the app is running from — the exe's folder when frozen
    by PyInstaller, otherwise this script's folder."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _find_tool(name):
    """Resolve an ffmpeg/ffprobe binary: prefer a copy shipped next to the
    app (so a bundled .exe needs zero setup) before falling back to PATH."""
    exe_name = name + (".exe" if os.name == "nt" else "")
    for candidate in (
        os.path.join(_app_dir(), exe_name),
        os.path.join(_app_dir(), "ffmpeg", "bin", exe_name),
    ):
        if os.path.isfile(candidate):
            return candidate
    return shutil.which(name)


FFMPEG = _find_tool("ffmpeg")
FFPROBE = _find_tool("ffprobe")


def check_ffmpeg_installed():
    """Raise a clear error if ffmpeg / ffprobe can't be found (neither
    bundled next to the app nor on PATH)."""
    if FFMPEG is None or FFPROBE is None:
        raise FFmpegNotFoundError(
            "FFmpeg was not found.\n\n"
            "Either place ffmpeg.exe and ffprobe.exe in the same folder as "
            "this app, or install FFmpeg and add it to PATH:\n"
            "  Windows: https://www.gyan.dev/ffmpeg/builds/ (add the bin folder to PATH)\n"
            "  macOS:   brew install ffmpeg\n"
            "  Linux:   sudo apt install ffmpeg"
        )


def get_duration_seconds(input_path: str) -> float:
    """Use ffprobe to get the duration of a media file, in seconds."""
    cmd = [
        FFPROBE or "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        input_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return 0.0


# Resolutions offered in the UI -> (width, height), or None for "keep original"
RESOLUTIONS = {
    "Original (no resize)": None,
    "3840x2160 (4K)": (3840, 2160),
    "1920x1080 (Full HD)": (1920, 1080),
    "1280x720 (720p)": (1280, 720),
    "854x480 (480p)": (854, 480),
    "640x360 (360p)": (640, 360),
}

VIDEO_FORMATS = {
    # container : ffmpeg video codec choices available for that container
    "mp4": ["h264", "h265"],
    "mkv": ["h264", "h265", "vp9"],
    "mov": ["h264", "h265"],
    "webm": ["vp9"],
    "avi": ["mpeg4"],
}

CODEC_MAP = {
    "h264": "libx264",
    "h265": "libx265",
    "vp9": "libvpx-vp9",
    "mpeg4": "mpeg4",
}

MP3_BITRATES = ["128k", "160k", "192k", "256k", "320k"]

# ffmpeg -r values. "30000/1001" is exactly 29.97fps (drop-frame rate).
FRAMERATES = {
    "Native (source frame rate)": None,
    "24 fps": "24",
    "25 fps": "25",
    "29.97 fps": "30000/1001",
}

COLORSPACES = {
    "Rec.709 (SDR)": {
        "primaries": "bt709",
        "trc": "bt709",
        "colorspace": "bt709",
        "pix_fmt": "yuv420p",       # 8-bit is standard for Rec.709 SDR delivery
    },
    "Rec.2020 (HDR)": {
        "primaries": "bt2020",
        "trc": "smpte2084",         # PQ transfer function, standard for HDR10
        "colorspace": "bt2020nc",
        "pix_fmt": "yuv420p10le",   # HDR requires 10-bit, not 8-bit
    },
}

BITRATE_RANGE_MBPS = (1, 100)   # slider range
DEFAULT_BITRATE_MBPS = 20

# Audio option labels shown in the UI, and which containers support them.
# (WebM only accepts Opus/Vorbis; AVI's AAC support is unreliable in practice;
# PCM works cleanly in MP4/MOV/MKV.)
AUDIO_PCM = "PCM 16-bit (48kHz, uncompressed)"
AUDIO_AAC = "AAC (compressed, 192kbps)"
AUDIO_OPUS = "Opus (compressed, 192kbps)"
AUDIO_NONE = "No audio"

AUDIO_OPTIONS_BY_CONTAINER = {
    "mp4": [AUDIO_PCM, AUDIO_AAC, AUDIO_NONE],
    "mkv": [AUDIO_PCM, AUDIO_AAC, AUDIO_OPUS, AUDIO_NONE],
    "mov": [AUDIO_PCM, AUDIO_AAC, AUDIO_NONE],
    "avi": [AUDIO_PCM, AUDIO_NONE],
    "webm": [AUDIO_OPUS, AUDIO_NONE],
}


def build_video_command(
    input_path: str,
    output_path: str,
    container: str,
    codec_key: str,
    resolution_key: str,
    bitrate_mbps: float,
    framerate_key: str,
    colorspace_key: str,
    audio_label: str,
):
    """
    Build an ffmpeg command list for a video-to-video conversion.

    Defaults to a broadcast/OTT-style delivery spec (direct bitrate control,
    explicit frame rate, explicit color space, forced-progressive output,
    uncompressed audio) but every field is independently overridable —
    format/codec/resolution/bitrate/framerate/color-space/audio are all
    plain parameters, not locked together.
    """
    codec = CODEC_MAP[codec_key]
    color = COLORSPACES[colorspace_key]
    fps_value = FRAMERATES[framerate_key]
    scale = RESOLUTIONS.get(resolution_key)

    cmd = [FFMPEG or "ffmpeg", "-y", "-i", input_path]

    if fps_value:
        cmd += ["-r", fps_value]

    # bwdif with deint=interlaced only touches frames actually flagged as
    # interlaced, and passes progressive frames through untouched — this
    # guarantees progressive output regardless of source, with no visible
    # effect on sources that are already progressive.
    vf_parts = ["bwdif=mode=send_frame:deint=interlaced"]
    if scale:
        vf_parts.append(f"scale={scale[0]}:{scale[1]}")
    cmd += ["-vf", ",".join(vf_parts)]

    cmd += ["-c:v", codec]

    # Direct bitrate control with a hard ceiling, rather than CRF, since a
    # specific bitrate is usually a stated requirement, not just a quality dial.
    bitrate_str = f"{bitrate_mbps}M"
    cmd += ["-b:v", bitrate_str, "-maxrate", bitrate_str, "-bufsize", f"{bitrate_mbps * 2}M"]

    cmd += ["-pix_fmt", color["pix_fmt"]]
    cmd += [
        "-color_primaries", color["primaries"],
        "-color_trc", color["trc"],
        "-colorspace", color["colorspace"],
    ]

    if audio_label == AUDIO_PCM:
        cmd += ["-c:a", "pcm_s16le", "-ar", "48000"]
    elif audio_label == AUDIO_AAC:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    elif audio_label == AUDIO_OPUS:
        cmd += ["-c:a", "libopus", "-b:a", "192k", "-ar", "48000"]
    else:  # AUDIO_NONE
        cmd += ["-an"]

    cmd += [output_path]
    return cmd


def build_audio_command(input_path: str, output_path: str, bitrate: str):
    """Build an ffmpeg command list for extracting audio as MP3 (legacy/simple mode)."""
    return [
        FFMPEG or "ffmpeg", "-y",
        "-i", input_path,
        "-vn",                      # drop video stream
        "-c:a", "libmp3lame",
        "-b:a", bitrate,
        output_path,
    ]


# ---------------------------------------------------------------------------
# Audio extraction with data-licensing-style specs
#
# Defaults follow a typical "Preferred / Ideal" spec for speech audio data:
#   Format: WAV or FLAC (lossless), Bit depth: 24-bit,
#   Sample rate: 16-48kHz (48kHz used as default), Channels: stereo.
# Minimum-acceptable fallbacks (16-bit, 8kHz, mono, MP3) remain selectable.
# ---------------------------------------------------------------------------

AUDIO_EXTRACT_FORMATS = ["FLAC (lossless)", "WAV (lossless)", "MP3 (compressed, fallback)"]

AUDIO_BIT_DEPTHS = ["16-bit (minimum)", "24-bit (preferred)"]

AUDIO_SAMPLE_RATES = {
    "8000 Hz (telephony minimum)": 8000,
    "16000 Hz": 16000,
    "22050 Hz": 22050,
    "24000 Hz (strongly preferred minimum)": 24000,
    "44100 Hz": 44100,
    "48000 Hz (preferred)": 48000,
}

AUDIO_CHANNELS = {
    "Mono (acceptable)": 1,
    "Stereo (preferred)": 2,
}

AUDIO_EXTRACT_BITRATES = ["24k", "64k", "128k", "192k", "256k", "320k"]


def build_audio_extract_command(
    input_path: str,
    output_path: str,
    format_key: str,
    bit_depth_key: str,
    sample_rate_key: str,
    channels_key: str,
    mp3_bitrate: str = "192k",
):
    """
    Build an ffmpeg command for extracting audio with explicit control over
    format, bit depth, sample rate, and channel count — e.g. for matching a
    data-delivery or licensing spec rather than just "make an mp3".
    """
    sample_rate = AUDIO_SAMPLE_RATES[sample_rate_key]
    channels = AUDIO_CHANNELS[channels_key]

    cmd = [FFMPEG or "ffmpeg", "-y", "-i", input_path, "-vn", "-ar", str(sample_rate), "-ac", str(channels)]

    if format_key.startswith("FLAC"):
        cmd += ["-c:a", "flac"]
        if bit_depth_key.startswith("24"):
            cmd += ["-sample_fmt", "s32", "-bits_per_raw_sample", "24"]
        else:
            cmd += ["-sample_fmt", "s16"]
    elif format_key.startswith("WAV"):
        if bit_depth_key.startswith("24"):
            cmd += ["-c:a", "pcm_s24le"]
        else:
            cmd += ["-c:a", "pcm_s16le"]
    else:  # MP3 fallback — bit depth doesn't apply to a compressed format
        cmd += ["-c:a", "libmp3lame", "-b:a", mp3_bitrate]

    cmd += [output_path]
    return cmd


TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")


def run_ffmpeg(cmd, total_duration, on_progress=None, on_line=None):
    """
    Run an ffmpeg command, streaming stderr to parse progress.

    on_progress(percent: float) is called as progress updates (0-100).
    on_line(text: str) is called with each raw line of ffmpeg output (for a log view).
    Raises RuntimeError with the last lines of ffmpeg output if it fails.
    """
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    last_lines = []
    for line in process.stdout:
        last_lines.append(line)
        if len(last_lines) > 40:
            last_lines.pop(0)

        if on_line:
            on_line(line.strip())

        match = TIME_RE.search(line)
        if match and total_duration > 0 and on_progress:
            h, m, s = match.groups()
            elapsed = int(h) * 3600 + int(m) * 60 + float(s)
            percent = min(100.0, (elapsed / total_duration) * 100)
            on_progress(percent)

    process.wait()

    if process.returncode != 0:
        raise RuntimeError("FFmpeg failed:\n" + "".join(last_lines[-15:]))

    if on_progress:
        on_progress(100.0)


def command_to_string(cmd):
    """For displaying/logging the exact command being run."""
    return " ".join(shlex.quote(part) for part in cmd)