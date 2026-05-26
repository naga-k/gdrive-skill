---
name: gdrive
description: >
  Google Drive workflows backed by the gws CLI
  (https://github.com/googleworkspace/cli). Use this skill bundle whenever the
  user wants to download, upload, inspect, list, or share Google Drive files
  from the command line. Also use it when the user pastes a Drive share URL and
  asks to fetch the file, find a transcript, or move it locally.
---

# gdrive — Google Drive via `gws` CLI

Workflow layer over the `gws` Google Workspace CLI. This bundle does NOT
reimplement Drive API calls — it documents the right `gws` invocations and
wraps multi-step flows as thin scripts.

## Prerequisites

- `gws` on `$PATH` (`brew install googleworkspace-cli`)
- OAuth client JSON at `~/.config/gws/client_secret.json` plus a logged-in
  token (see [`references/setup.md`](references/setup.md) for the one-time
  setup)

Check state with:
```bash
gws auth status
```

## Scripts

Helpers in `scripts/` extend `gws` with multi-account isolation and a
named-tracker registry. Reach for these before the raw env-var pattern
in "Multi-account (low-level)" below.

- `scripts/gws-account`: add, list, use, show named accounts (each isolated under `~/.config/gws/accounts/<name>/`).
- `scripts/gws-as`: one-shot wrapper to run any `gws ...` command under a specific account.
- `scripts/gws-sheet`: register, list, info, read named Sheets trackers (read-only today).
- `scripts/gdrive_download.py`: used by the `download` sub-skill.

Design context: [`docs/2026-05-20-multi-account-design.md`](docs/2026-05-20-multi-account-design.md).

## Sub-skills

- [`download`](download/SKILL.md) — download a Drive video and obtain its
  transcript (captions track, sibling Doc, or locally generated).

## Quick reference (one-shot Drive operations)

```bash
# Search
gws drive files list --params '{"q": "name contains '\''meeting'\''", "pageSize": 20}' --format table

# Inspect
gws drive files get --params '{"fileId": "<ID>", "fields": "id,name,mimeType,size,parents"}'

# Download binary (streaming). files.download is async/long-running — don't use it.
# --output is sandboxed to cwd; run this from the directory you want the file in.
gws drive files get --params '{"fileId": "<ID>", "alt": "media"}' --output out.mp4

# Export Google-native doc to plain text
gws drive files export --params '{"fileId": "<DOC_ID>", "mimeType": "text/plain"}' --output out.txt

# Discover any method's full parameter schema
gws schema drive.files.get
```

## Account management

Each named account lives under `~/.config/gws/accounts/<name>/` with its
own `client_secret.json`, `credentials.enc`, and `token_cache.json`. Token
caches no longer collide across accounts.

```bash
scripts/gws-account add <name>     # create the account dir and run `gws auth login` against it
scripts/gws-account list           # all configured accounts, their email, which is default
scripts/gws-account use <name>     # set the default account (writes ~/.config/gws/active-account)
scripts/gws-account show           # print the current default account name
```

Per-invocation override (does not change the default):

```bash
scripts/gws-as <name> <gws-args...>
# e.g. gws-as work drive files list --params '{"pageSize": 5}'
```

## Named-tracker reads

Register frequently-touched Sheets by short name and route them
automatically to the right account. Registry lives at
`~/.config/gws/registry.toml`. Read-only today.

```bash
scripts/gws-sheet register <name> <url-or-id>   # probes accounts, confirms, writes the entry
scripts/gws-sheet list                          # every registered tracker
scripts/gws-sheet info <name>                   # name, sheet_id, account, list of tabs
scripts/gws-sheet read <name> [range]           # read a range (default A:Z), --format json|table
```

Writes (`append`, `update`, `clear`) are intentionally not exposed by
`gws-sheet`. Until Phase 3 lands, do writes via the low-level wrapper:

```bash
scripts/gws-as <account> sheets spreadsheets values update --params '{...}'
```

## Multi-account (low-level, when wrappers don't fit)

Fallback for cases the wrappers above don't cover (one-off accounts not
registered via `gws-account`, or scripts that prefer raw env vars). `gws`
keeps a single active account at `~/.config/gws/`. Select a different
credentials file per invocation:

```bash
GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=~/.config/gws/accounts/work.json \
  gws drive files list
```

The `download` sub-skill exposes this as a `--account PATH` flag.
