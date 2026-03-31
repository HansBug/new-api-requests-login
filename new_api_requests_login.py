#!/usr/bin/env python3
"""Log in to a New API deployment with requests and fetch user profile data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.parse import urljoin

import requests


DEFAULT_BASE_URL = "https://your-new-api.example.com"
DEFAULT_TIMEOUT = 20


class NewAPILoginError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Log in to a New API deployment with requests and fetch user profile data.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("NEW_API_BASE_URL", DEFAULT_BASE_URL),
        help="Deployment base URL. Set NEW_API_BASE_URL or pass --base-url.",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("NEW_API_USERNAME"),
        help="Login username. Can also come from NEW_API_USERNAME.",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("NEW_API_PASSWORD"),
        help="Login password. Can also come from NEW_API_PASSWORD.",
    )
    parser.add_argument(
        "--twofa-code",
        default=os.getenv("NEW_API_2FA_CODE"),
        help="Optional 2FA or backup code. Used only when the account requires 2FA.",
    )
    parser.add_argument(
        "--turnstile-token",
        default=os.getenv("NEW_API_TURNSTILE_TOKEN", ""),
        help="Optional Cloudflare Turnstile token if the site enables it.",
    )
    parser.add_argument(
        "--with-groups",
        action="store_true",
        help="Fetch /api/user/self/groups after login.",
    )
    parser.add_argument(
        "--with-models",
        action="store_true",
        help="Fetch /api/user/models after login.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds. Default: {DEFAULT_TIMEOUT}",
    )
    return parser.parse_args()


def ensure_required_config(args: argparse.Namespace) -> None:
    if not args.base_url or args.base_url == DEFAULT_BASE_URL:
        raise NewAPILoginError(
            "missing base URL: use --base-url or NEW_API_BASE_URL",
        )
    if not args.username or not args.password:
        raise NewAPILoginError(
            "missing credentials: use --username/--password or NEW_API_USERNAME/NEW_API_PASSWORD",
        )


def decode_json(response: requests.Response) -> dict[str, Any]:
    try:
        return response.json()
    except ValueError as exc:
        raise NewAPILoginError(
            f"expected JSON from {response.request.method} {response.url}, got: {response.text[:300]!r}",
        ) from exc


def require_success(payload: dict[str, Any], action: str) -> dict[str, Any]:
    if not payload.get("success"):
        raise NewAPILoginError(f"{action} failed: {payload.get('message') or payload}")
    data = payload.get("data")
    if data is None:
        raise NewAPILoginError(f"{action} returned no data")
    return data


def build_session(timeout: int) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "new-api-requests-login/1.0",
            "Cache-Control": "no-store",
            "Accept": "application/json, text/plain, */*",
        }
    )
    session.request = _wrap_request_with_timeout(session.request, timeout)
    return session


def _wrap_request_with_timeout(request_method, timeout: int):
    def wrapped(method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", timeout)
        return request_method(method, url, **kwargs)

    return wrapped


def login(
    session: requests.Session,
    base_url: str,
    username: str,
    password: str,
    twofa_code: str | None = None,
    turnstile_token: str = "",
) -> dict[str, Any]:
    login_url = urljoin(base_url.rstrip("/") + "/", "api/user/login")
    if turnstile_token:
        login_url = f"{login_url}?turnstile={turnstile_token}"
    response = session.post(
        login_url,
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    data = require_success(decode_json(response), "login")

    if data.get("require_2fa"):
        if not twofa_code:
            raise NewAPILoginError(
                "account requires 2FA; pass --twofa-code or NEW_API_2FA_CODE",
            )
        verify_url = urljoin(base_url.rstrip("/") + "/", "api/user/login/2fa")
        verify_response = session.post(verify_url, json={"code": twofa_code})
        verify_response.raise_for_status()
        data = require_success(decode_json(verify_response), "2FA verification")

    required_keys = {"id", "username", "display_name", "group", "role", "status"}
    missing = sorted(required_keys - data.keys())
    if missing:
        raise NewAPILoginError(f"login response missing keys: {', '.join(missing)}")
    return data


def fetch_user_self(
    session: requests.Session,
    base_url: str,
    user_id: int,
) -> dict[str, Any]:
    session.headers["New-API-User"] = str(user_id)
    response = session.get(urljoin(base_url.rstrip("/") + "/", "api/user/self"))
    response.raise_for_status()
    return require_success(decode_json(response), "fetch user profile")


def fetch_optional(session: requests.Session, base_url: str, path: str) -> Any:
    response = session.get(urljoin(base_url.rstrip("/") + "/", path.lstrip("/")))
    response.raise_for_status()
    return require_success(decode_json(response), f"fetch {path}")


def main() -> int:
    args = parse_args()

    try:
        ensure_required_config(args)
        session = build_session(args.timeout)
        login_data = login(
            session=session,
            base_url=args.base_url,
            username=args.username,
            password=args.password,
            twofa_code=args.twofa_code,
            turnstile_token=args.turnstile_token,
        )
        profile = fetch_user_self(
            session=session,
            base_url=args.base_url,
            user_id=int(login_data["id"]),
        )
        result: dict[str, Any] = {
            "login": login_data,
            "profile": profile,
        }
        if args.with_groups:
            result["groups"] = fetch_optional(session, args.base_url, "/api/user/self/groups")
        if args.with_models:
            result["models"] = fetch_optional(session, args.base_url, "/api/user/models")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except requests.HTTPError as exc:
        body = exc.response.text[:600] if exc.response is not None else ""
        print(f"HTTP error: {exc}\n{body}", file=sys.stderr)
        return 1
    except NewAPILoginError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
