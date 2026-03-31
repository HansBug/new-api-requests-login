# airouter-requests-login

Use `requests` to log in to a New API / Airouter deployment and fetch real user profile data from `/api/user/self`.

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
python airouter_requests_login.py \
  --base-url 'https://airouter.service.itstudio.club' \
  --username 'your_username' \
  --password 'your_password' \
  --with-groups
```

### Option 2: environment variables

```bash
export AIROUTER_BASE_URL='https://airouter.service.itstudio.club'
export AIROUTER_USERNAME='your_username'
export AIROUTER_PASSWORD='your_password'
python airouter_requests_login.py --with-groups --with-models
```

## Optional Flags

- `--twofa-code`: TOTP code or backup code if the account requires 2FA
- `--turnstile-token`: pass a Turnstile token if the target site enables Turnstile
- `--with-groups`: also fetch `/api/user/self/groups`
- `--with-models`: also fetch `/api/user/models`
- `--timeout`: request timeout in seconds

## Output

On success the script prints JSON like:

```json
{
  "login": {
    "id": 100,
    "username": "example",
    "display_name": "example",
    "group": "default",
    "role": 1,
    "status": 1
  },
  "profile": {
    "id": 100,
    "username": "example",
    "display_name": "example",
    "group": "default"
  }
}
```

## Notes

- The repository intentionally does not store any credentials.
- If the target deployment has custom anti-bot or SSO logic enabled, the login process may require extra parameters.
- For standard password login on New API style deployments, this script is usually enough.
