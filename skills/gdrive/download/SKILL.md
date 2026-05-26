---
name: gdrive-download
description: >
  Download a Google Drive video and obtain its transcript. Use this skill when
  the user pastes a Drive share URL (drive.google.com/file/d/...) or raw file
  ID and asks to download the video, grab its captions, fetch the meeting
  transcript, or save it locally. Handles auth via the gws CLI.
---

# gdrive-download — Video + transcript from Drive

Thin wrapper around `gws drive files {get,download,list,export}` that handles
the common "download this shared video and its transcript" workflow.

## Usage

The script lives at `scripts/gdrive_download.py` relative to the **gdrive skill root**
(one level up from this sub-skill). When this skill loads, the base directory header
shows the install path — use that to construct the full path, or add the `scripts/`
directory to your `$PATH` for direct terminal invocation.

```bash
python3 <gdrive-skill-root>/scripts/gdrive_download.py <drive_url_or_id> \
    [--out-dir PATH]                          # default: media/downloads/<slug>/
    [--transcript auto|sibling|generate|skip] # default: auto
    [--account NAME]                          # gws account from `gws-account add`
```

`auto` tries in order: caption track on the video → sibling Doc in the same
Drive folder → skip (does NOT generate locally unless `generate` is explicit).

## Flow (what the script actually does)

1. **Parse input.** Accept `https://drive.google.com/file/d/<ID>/view`,
   `https://drive.google.com/open?id=<ID>`, or a bare file ID.
2. **Fetch metadata** — `gws drive files get` with fields
   `id,name,mimeType,size,parents`. Refuse non-video mimeTypes unless user
   confirms, since `files.download` only works on binary content (Docs need
   `files.export`).
3. **Download video** — `gws drive files get --params '{"fileId":"<ID>","alt":"media"}' --output <relative_path>`. Use `files.get` with `alt=media` (streaming); NOT `files.download`, which is a long-running async POST. `gws` rejects `--output` paths outside `cwd`, so the wrapper `cd`s to the parent directory first.
4. **Transcript resolution** (only when `--transcript != skip`):
   - **Sibling lookup**: `gws drive files list` with
     `q='<parent_id>' in parents and (mimeType='application/vnd.google-apps.document' or mimeType='text/plain')`
     and name starting with the video's stem. If found, export Doc via
     `files.export` with `mimeType=text/plain`, or download text files directly.
   - **Generate** (`--transcript generate`): extract low-bitrate mono MP3
     with `ffmpeg -i video.mp4 -vn -acodec libmp3lame -ab 32k -ac 1 -ar 16000 audio.mp3`
     (~15 MB / hour — faster upload than WAV). Two backends:
     - **Inline (default)**: uses `$ASSEMBLYAI_API_KEY` if set (AssemblyAI with
       speaker diarization), otherwise falls back to the local `whisper` CLI.
     - Bring your own: swap in any transcription script by post-processing the
       audio file the script writes.
5. **Write outputs** — always `<slug>.mp4`; optionally `<slug>.transcript.txt`.

## Defaults and conventions

- `<slug>` = lowercased filename with non-alphanumerics replaced by `_`, e.g.
  `"Design Review.mp4"` → `design_review`.
- Output directory: `media/downloads/<slug>/` (relative to the project root).
- Progress: `gws` prints download progress to stderr; the script mirrors it.

## Common failure modes

- **`403 Forbidden` on `files.get`**: the active gws account doesn't have
  access. Either ask the owner to share with that account, or run with
  `--account <name>` naming an account (from `gws-account add`) that does.
- **`mimeType` is `application/vnd.google-apps.document`** (or similar): the
  file isn't a video — user probably pasted the wrong link, or it's the
  transcript Doc itself. Use `gws drive files export` instead.
- **No sibling transcript found**: common for user-uploaded videos. Suggest
  `--transcript generate` if the user wants one.
- **Drive quota / rate limit**: retry with `--page-delay 500` on listing; for
  downloads, `gws` streams so rate limits are rare.

## Example — download today's meeting video

```bash
python3 <gdrive-skill-root>/scripts/gdrive_download.py \
    "https://drive.google.com/file/d/<YOUR_FILE_ID>/view" \
    --out-dir media/downloads/team_review/ \
    --transcript auto
```
