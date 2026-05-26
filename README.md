# gdrive-skill

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugin that gives Claude a thin, reliable layer over the [`gws` Google Workspace CLI](https://github.com/rclone/google-workspace-cli) — covering multi-account auth isolation, a named Sheets tracker registry, and Drive video download with automatic transcript extraction.

This skill does **not** reimplement any Drive/Sheets API calls. It documents the right `gws` invocations and wraps multi-step flows as thin Python/Bash scripts.

---

## Features

- **Multi-account isolation** — each Google account lives in its own `~/.config/gws/accounts/<name>/` directory; token caches never collide
- **Named tracker registry** — register Sheets by short name (`gws-sheet register uat <url>`); read them without pasting URLs or remembering which account owns what
- **Drive video download** — streaming download via `gws` with automatic sibling-transcript lookup (Drive Doc or `.txt` in the same folder) or on-demand local generation via AssemblyAI / Whisper
- **One-shot account switching** — `gws-as <account> <cmd...>` runs any `gws` command under a specific account without changing the default

---

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
- `gws` CLI on `$PATH`: `brew install googleworkspace-cli`
- An OAuth 2.0 client JSON — see **Setup** below

---

## Install as a Claude Code plugin

```
/plugins install github:naga-k/gdrive-skill
```

This drops the skill at `~/.claude/skills/gdrive/` and makes `/gdrive` available in Claude Code.

### Manual install

```bash
git clone https://github.com/naga-k/gdrive-skill.git /tmp/gdrive-skill
cp -r /tmp/gdrive-skill/.claude/skills/gdrive ~/.claude/skills/gdrive
```

---

## One-time OAuth setup

See [`references/setup.md`](.claude/skills/gdrive/references/setup.md) for the full walkthrough. Quick version:

1. Create a GCP project and enable the Drive (and optionally Sheets) API
2. Download an OAuth Desktop client JSON → `~/.config/gws/client_secret.json`
3. `gws auth login --services drive`

---

## Account management

```bash
# Add a new named account (creates isolated config dir + runs gws auth login)
scripts/gws-account add personal
scripts/gws-account add work

# List accounts, their email, and which is the default
scripts/gws-account list

# Set the default account
scripts/gws-account use work

# Run any gws command under a specific account without changing the default
scripts/gws-as personal drive files list --params '{"pageSize": 5}'
```

---

## Named Sheets tracker registry

Register frequently-touched Sheets by short name. The registry probes all configured accounts to find which one has access, then saves `(name, sheet_id, account)` in `~/.config/gws/registry.toml`.

```bash
# Register a tracker (probes accounts, asks for confirmation)
scripts/gws-sheet register uat "https://docs.google.com/spreadsheets/d/<ID>/edit"

# List all registered trackers
scripts/gws-sheet list

# Show tabs and metadata for a tracker
scripts/gws-sheet info uat

# Read a range (default: A:Z on first tab)
scripts/gws-sheet read uat
scripts/gws-sheet read uat "Sheet1!A1:F50" --format table
```

> Writes (`append`, `update`, `clear`) are not exposed by `gws-sheet`. Use `gws-as <account> sheets ...` directly for those.

---

## Drive video download + transcript

```bash
python3 ~/.claude/skills/gdrive/scripts/gdrive_download.py \
    "https://drive.google.com/file/d/<YOUR_FILE_ID>/view" \
    [--out-dir PATH]                          # default: media/downloads/<slug>/
    [--transcript auto|sibling|generate|skip] # default: auto
    [--account PATH]                          # alternate credentials JSON
```

`--transcript auto` tries: sibling Doc/text file in the same Drive folder → skip. Use `generate` to invoke AssemblyAI (set `$ASSEMBLYAI_API_KEY`) or the local `whisper` CLI.

---

## Quick Drive reference

```bash
# Search
gws drive files list --params '{"q": "name contains '\''meeting'\''", "pageSize": 20}' --format table

# Download binary (streaming)
gws drive files get --params '{"fileId": "<ID>", "alt": "media"}' --output out.mp4

# Export a Google Doc to plain text
gws drive files export --params '{"fileId": "<DOC_ID>", "mimeType": "text/plain"}' --output out.txt

# Discover any method's parameter schema
gws schema drive.files.get
```

---

## License

MIT
