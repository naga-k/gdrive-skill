#!/usr/bin/env python3
"""Download a Google Drive video and obtain its transcript via the gws CLI.

Usage:
    gdrive_download.py <url_or_id> [--out-dir PATH]
                                   [--transcript auto|sibling|generate|skip]
                                   [--account NAME]

See skills/gdrive/download/SKILL.md in the plugin repo for the full flow.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


# ---------- input parsing ----------

_FILE_ID_RE = re.compile(r"[A-Za-z0-9_-]{20,}")


def parse_file_id(url_or_id: str) -> str:
    """Accept a Drive URL or bare file ID; return the file ID."""
    m = re.search(r"/file/d/([A-Za-z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)
    if _FILE_ID_RE.fullmatch(url_or_id):
        return url_or_id
    raise SystemExit(f"Could not extract a Drive file ID from: {url_or_id!r}")


def slugify(name: str) -> str:
    stem = Path(name).stem
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_") or "download"


# ---------- gws wrapper ----------

def resolve_config_dir(account: str) -> Path:
    """Map an --account value to a gws config dir.

    A bare name (e.g. ``work``) → ``~/.config/gws/accounts/<name>/``, the layout
    `gws-account add` creates. A value containing a path separator (or ``~``) is
    treated as an explicit config-dir path. Either way we set
    GOOGLE_WORKSPACE_CLI_CONFIG_DIR — the env var that isolates logged-in tokens
    per account. (GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE only swaps the OAuth
    client, not the authenticated user, so it does NOT achieve account isolation.)
    """
    if os.sep in account or (os.altsep and os.altsep in account) or account.startswith("~"):
        return Path(account).expanduser()
    return Path.home() / ".config" / "gws" / "accounts" / account


def gws(
    args: list[str],
    account: str | None = None,
    capture: bool = True,
    cwd: Path | None = None,
) -> str:
    """Run a gws command, return stdout. Inherit stderr so progress is visible.

    `gws` sandboxes `--output` paths to the current working directory, so any
    call that writes a file must pass `cwd=` as the base for a relative
    `--output`.
    """
    env = os.environ.copy()
    if account:
        env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = str(resolve_config_dir(account))
    try:
        result = subprocess.run(
            ["gws", *args],
            check=True,
            env=env,
            stdout=subprocess.PIPE if capture else None,
            stderr=None,
            text=True,
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError:
        raise SystemExit("gws not found on PATH. Install: brew install googleworkspace-cli")
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"gws failed (exit {e.returncode}): {' '.join(args)}")
    return result.stdout if capture else ""


def drive_get(file_id: str, fields: str, account: str | None) -> dict:
    params = json.dumps({"fileId": file_id, "fields": fields})
    out = gws(["drive", "files", "get", "--params", params], account=account)
    return json.loads(out)


def drive_list(query: str, fields: str, account: str | None) -> list[dict]:
    params = json.dumps({"q": query, "fields": f"files({fields})", "pageSize": 100})
    out = gws(["drive", "files", "list", "--params", params], account=account)
    return json.loads(out).get("files", [])


def _gws_output_cwd(out_path: Path) -> tuple[Path, str]:
    """Prepare an output path for gws: create parent dir, return (cwd, relative_path).

    gws rejects any --output that resolves outside the cwd, so we cd to the
    project root and pass a relative path.
    """
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Walk up until we find a directory that contains the out_path — use cwd
    # as the common ancestor. Simplest safe choice: the out_path's drive root
    # might be too loose; use the nearest existing ancestor.
    cwd = out_path.parent
    # Walk up until we find a directory we can write to — in practice,
    # out_path.parent works (we just created it). Relative path from there.
    rel = out_path.relative_to(cwd)
    return cwd, str(rel)


def drive_download(file_id: str, out_path: Path, account: str | None) -> None:
    # files.get with alt=media is the streaming download endpoint.
    # files.download (POST) is an async long-running operation and is NOT what we want.
    params = json.dumps({"fileId": file_id, "alt": "media"})
    cwd, rel = _gws_output_cwd(out_path)
    gws(
        ["drive", "files", "get", "--params", params, "--output", rel],
        account=account,
        capture=False,
        cwd=cwd,
    )


def drive_export(file_id: str, mime: str, out_path: Path, account: str | None) -> None:
    params = json.dumps({"fileId": file_id, "mimeType": mime})
    cwd, rel = _gws_output_cwd(out_path)
    gws(
        ["drive", "files", "export", "--params", params, "--output", rel],
        account=account,
        capture=False,
        cwd=cwd,
    )


# ---------- transcript strategies ----------

def find_sibling_transcript(
    video_meta: dict, account: str | None
) -> tuple[str, str] | None:
    """Look for a Doc or .txt in the same folder whose name starts with the video stem.

    Returns (file_id, mimeType) or None.
    """
    parents = video_meta.get("parents") or []
    if not parents:
        return None
    parent_id = parents[0]
    stem = Path(video_meta["name"]).stem
    escaped_stem = stem.replace("'", r"\'")
    query = (
        f"'{parent_id}' in parents and trashed = false and "
        f"(mimeType = 'application/vnd.google-apps.document' or mimeType = 'text/plain') and "
        f"name contains '{escaped_stem}'"
    )
    files = drive_list(query, "id,name,mimeType", account)
    if not files:
        return None
    # Prefer Docs over plain text; prefer names that start with the stem.
    files.sort(
        key=lambda f: (
            0 if f["name"].startswith(stem) else 1,
            0 if f["mimeType"] == "application/vnd.google-apps.document" else 1,
        )
    )
    return files[0]["id"], files[0]["mimeType"]


def generate_transcript(video_path: Path, out_path: Path) -> None:
    """Extract audio + transcribe locally. Uses AssemblyAI if key is set, else whisper."""
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH; needed to extract audio for transcription.")
    # Low-bitrate mono MP3 (~15 MB/hour) — far faster to upload than WAV.
    audio_path = video_path.with_suffix(".mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path),
         "-vn", "-acodec", "libmp3lame", "-ab", "32k", "-ac", "1", "-ar", "16000",
         str(audio_path)],
        check=True,
    )
    if os.environ.get("ASSEMBLYAI_API_KEY"):
        _transcribe_assemblyai(audio_path, out_path)
    elif shutil.which("whisper"):
        _transcribe_whisper(audio_path, out_path)
    else:
        raise SystemExit(
            "No transcription backend available. "
            "Set ASSEMBLYAI_API_KEY or install `pip install openai-whisper`."
        )


def _transcribe_assemblyai(audio_path: Path, out_path: Path) -> None:
    # Minimal inline client — avoids adding a dep. Upload, poll, write text.
    import time
    import urllib.request

    key = os.environ["ASSEMBLYAI_API_KEY"]
    headers = {"authorization": key}

    with audio_path.open("rb") as f:
        req = urllib.request.Request(
            "https://api.assemblyai.com/v2/upload", data=f.read(), headers=headers
        )
        upload_url = json.loads(urllib.request.urlopen(req).read())["upload_url"]

    req = urllib.request.Request(
        "https://api.assemblyai.com/v2/transcript",
        data=json.dumps({"audio_url": upload_url, "speaker_labels": True}).encode(),
        headers={**headers, "content-type": "application/json"},
    )
    tid = json.loads(urllib.request.urlopen(req).read())["id"]

    status_url = f"https://api.assemblyai.com/v2/transcript/{tid}"
    while True:
        time.sleep(3)
        result = json.loads(
            urllib.request.urlopen(urllib.request.Request(status_url, headers=headers)).read()
        )
        if result["status"] == "completed":
            # With speaker_labels the API returns per-utterance speakers; fall
            # back to the flat transcript if diarization yielded nothing.
            utterances = result.get("utterances") or []
            if utterances:
                text = "\n".join(f"Speaker {u['speaker']}: {u['text']}" for u in utterances)
            else:
                text = result.get("text") or ""
            out_path.write_text(text)
            return
        if result["status"] == "error":
            raise SystemExit(f"AssemblyAI error: {result.get('error')}")


def _transcribe_whisper(audio_path: Path, out_path: Path) -> None:
    subprocess.run(
        [
            "whisper", str(audio_path),
            "--model", "base",
            "--output_format", "txt",
            "--output_dir", str(out_path.parent),
        ],
        check=True,
    )
    produced = audio_path.with_suffix(".txt")
    if produced != out_path:
        produced.rename(out_path)


# ---------- main ----------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url_or_id", help="Drive share URL or bare file ID")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="Output directory (default: media/downloads/<slug>/)")
    ap.add_argument("--transcript", choices=["auto", "sibling", "generate", "skip"],
                    default="auto")
    ap.add_argument("--account", default=None,
                    help="gws account name (from `gws-account add`), or a config-dir path")
    args = ap.parse_args()

    file_id = parse_file_id(args.url_or_id)

    meta = drive_get(
        file_id,
        fields="id,name,mimeType,size,parents",
        account=args.account,
    )

    if not meta.get("mimeType", "").startswith("video/"):
        sys.stderr.write(
            f"Warning: mimeType is {meta.get('mimeType')!r}, not a video. "
            "Continuing anyway — Ctrl-C to abort.\n"
        )

    slug = slugify(meta["name"])
    out_dir = args.out_dir or Path("media/downloads") / slug
    video_path = out_dir / f"{slug}{Path(meta['name']).suffix or '.mp4'}"
    transcript_path = out_dir / f"{slug}.transcript.txt"

    sys.stderr.write(f"Downloading {meta['name']} ({meta.get('size', '?')} bytes) → {video_path}\n")
    drive_download(file_id, video_path, args.account)

    if args.transcript == "skip":
        return

    if args.transcript in ("auto", "sibling"):
        sibling = find_sibling_transcript(meta, args.account)
        if sibling:
            sib_id, sib_mime = sibling
            sys.stderr.write(f"Found sibling transcript ({sib_mime}), fetching...\n")
            if sib_mime == "application/vnd.google-apps.document":
                drive_export(sib_id, "text/plain", transcript_path, args.account)
            else:
                drive_download(sib_id, transcript_path, args.account)
            return
        if args.transcript == "sibling":
            sys.stderr.write("No sibling transcript found.\n")
            return

    if args.transcript == "generate":
        sys.stderr.write("Generating transcript from audio...\n")
        generate_transcript(video_path, transcript_path)


if __name__ == "__main__":
    main()
