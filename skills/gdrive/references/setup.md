# One-time setup — `gws` CLI auth

`gws` needs (1) an OAuth 2.0 client created in a Google Cloud project and (2) a
login token minted against that client. You do step 1 once per Google account;
step 2 once per account-scope combination.

## Step 1 — OAuth client

You have two paths. The second avoids installing `gcloud`.

### Option A — Automated (requires `gcloud`)

```bash
brew install --cask gcloud-cli    # cask was renamed from google-cloud-sdk
gcloud auth login
gws auth setup                    # creates GCP project + OAuth client for you
```

### Option B — Manual (no extra install)

1. Open <https://console.cloud.google.com/> and create (or select) a project.
2. Enable the Drive API: **APIs & Services → Library → "Google Drive API" → Enable**.
   Enable any other APIs you expect to use (Docs, Sheets, Calendar, Gmail, ...).
3. Configure OAuth consent:
   **APIs & Services → OAuth consent screen → External → fill required fields →
   add your Google email under "Test users"**. Leave the app in Testing mode —
   you don't need to publish it.
4. Create credentials:
   **APIs & Services → Credentials → Create credentials → OAuth client ID →
   Application type: Desktop app → Create → Download JSON**.
5. Move the JSON into place:
   ```bash
   mkdir -p ~/.config/gws
   mv ~/Downloads/client_secret_*.json ~/.config/gws/client_secret.json
   ```

## Step 2 — Log in

```bash
gws auth login --services drive     # scope picker limited to Drive
# or for everything:
gws auth login --full
```

The browser opens for consent. Token is cached encrypted under
`~/.config/gws/`. Verify:

```bash
gws auth status
gws drive files list --params '{"pageSize": 3}' --format table
```

## Multi-account setup

After logging in once, copy the active credentials file to a named path before
logging in as a different account:

```bash
mkdir -p ~/.config/gws/accounts
cp ~/.config/gws/credentials.json ~/.config/gws/accounts/personal.json

gws auth logout
gws auth login                      # log in as the other account
cp ~/.config/gws/credentials.json ~/.config/gws/accounts/work.json
```

Then pick per invocation:

```bash
GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=~/.config/gws/accounts/work.json \
  gws drive files list
```

The `gdrive-download` sub-skill exposes this as `--account PATH`.

## Scope tips

- `--services drive` requests `drive` scope (full Drive read/write). For
  download-only use cases the script also works with `drive.readonly` —
  request it via `gws auth login --scopes https://www.googleapis.com/auth/drive.readonly`.
- If `files.download` returns 403 on files shared with you (but works on files
  you own), you almost certainly logged in with `drive.file` scope only;
  re-login with `drive` or `drive.readonly`.
