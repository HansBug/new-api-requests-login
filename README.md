# new-api-requests-login

Use `requests` to log in to a New API deployment and fetch real user profile data from `/api/user/self`.

## What This Solves

Some New API deployments look simple at first glance, but the dashboard flow has one non-obvious detail:

1. `POST /api/user/login` with a JSON body.
2. Keep the returned `session` cookie.
3. Add `New-API-User: <user_id>` on later authenticated requests.
4. Then call `/api/user/self` to confirm the login and fetch personal data.

This repository automates that flow with a small Python script.

## Requirements

- Python 3.9+
- `requests`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Option 1: command line arguments

```bash
python new_api_requests_login.py \
  --base-url 'https://your-new-api.example.com' \
  --username 'your_username' \
  --password 'your_password' \
  --with-groups
```

### Option 2: environment variables

```bash
cp .env.example .env
source .env
python new_api_requests_login.py
```

The script only reads real environment variables from the current process. `.env` is just a shell helper file, so load it with `source .env` first if you want to use that format.

## Programmatic Usage

```python
from new_api_requests_login import Client

client = Client()
auth_result = client.auth("your_username", "your_password")

if auth_result.success:
    print(auth_result.profile)
else:
    print(auth_result.error.to_dict())
```

## Optional Flags

- `--twofa-code`: TOTP code or backup code if the account requires 2FA
- `--turnstile-token`: pass a Turnstile token if the target site enables Turnstile
- `--with-groups`: also fetch `/api/user/self/groups`
- `--with-models`: also fetch `/api/user/models`
- `--timeout`: request timeout in seconds

## Output

The CLI prints human-readable terminal output instead of raw JSON.

Successful authentication looks like:

```text
[OK] authentication succeeded
  Deployment   : https://your-new-api.example.com
  User ID      : 100
  Username     : example
  Display Name : example
  Group        : default
  Role         : 1
  Status       : 1
  Quota        : 123,456
  Used Quota   : 654,321
  Requests     : 42
```

Failed authentication prints a structured debug-friendly error block to `stderr`, including the failed step, request metadata, and server response content when available.

When the terminal supports ANSI colors, success and failure markers are highlighted automatically.

## Notes

- The repository intentionally does not store any deployment-specific credentials.
- The committed `.env.example` uses placeholder values; keep your real `.env` local.
- If the target deployment has custom anti-bot or SSO logic enabled, the login process may require extra parameters.
- For standard password login on New API style deployments, this script is usually enough.
