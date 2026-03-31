#!/usr/bin/env python3
"""Log in to a New API deployment, optionally run daily check-in, and fetch user profile data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests


DEFAULT_TIMEOUT = 20
MAX_ERROR_BODY = 1000


@dataclass
class ErrorDetail:
    type: str
    step: str
    message: str
    exception_type: str | None = None
    method: str | None = None
    url: str | None = None
    status_code: int | None = None
    response_json: Any | None = None
    response_body_excerpt: str | None = None
    details: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": self.type,
            "step": self.step,
            "message": self.message,
        }
        if self.exception_type:
            data["exception_type"] = self.exception_type
        if self.method:
            data["method"] = self.method
        if self.url:
            data["url"] = self.url
        if self.status_code is not None:
            data["status_code"] = self.status_code
        if self.response_json is not None:
            data["response_json"] = self.response_json
        if self.response_body_excerpt:
            data["response_body_excerpt"] = self.response_body_excerpt
        if self.details is not None:
            data["details"] = self.details
        return data


class NewAPIClientError(RuntimeError):
    def __init__(self, detail: ErrorDetail):
        super().__init__(detail.message)
        self.detail = detail


@dataclass
class AuthResult:
    success: bool
    message: str
    login: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None
    error: ErrorDetail | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "success": self.success,
            "message": self.message,
        }
        if self.login is not None:
            data["login"] = self.login
        if self.profile is not None:
            data["profile"] = self.profile
        if self.error is not None:
            data["error"] = self.error.to_dict()
        return data


@dataclass
class CheckinResult:
    success: bool
    message: str
    already_checked_in: bool = False
    payload: dict[str, Any] | None = None
    error: ErrorDetail | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "success": self.success,
            "message": self.message,
            "already_checked_in": self.already_checked_in,
        }
        if self.payload is not None:
            data["payload"] = self.payload
        if self.error is not None:
            data["error"] = self.error.to_dict()
        return data


class Client:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        turnstile_token: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        resolved_base_url = base_url if base_url is not None else os.getenv("NEW_API_BASE_URL")
        resolved_turnstile = (
            turnstile_token
            if turnstile_token is not None
            else os.getenv("NEW_API_TURNSTILE_TOKEN", "")
        )
        self.base_url = (resolved_base_url or "").rstrip("/")
        self.timeout = timeout
        self.turnstile_token = resolved_turnstile or ""
        self.session = session or self._build_session(timeout)
        self.last_auth_result: AuthResult | None = None

    def auth(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        twofa_code: str | None = None,
    ) -> AuthResult:
        resolved_username = username if username is not None else os.getenv("NEW_API_USERNAME")
        resolved_password = password if password is not None else os.getenv("NEW_API_PASSWORD")
        resolved_twofa = twofa_code if twofa_code is not None else os.getenv("NEW_API_2FA_CODE")
        self.session.headers.pop("New-API-User", None)

        if not self.base_url:
            detail = ErrorDetail(
                type="configuration_error",
                step="configuration",
                message="missing base URL: use --base-url or NEW_API_BASE_URL",
                details={"required": ["NEW_API_BASE_URL"]},
            )
            result = AuthResult(success=False, message=detail.message, error=detail)
            self.last_auth_result = result
            return result
        if not resolved_username or not resolved_password:
            detail = ErrorDetail(
                type="configuration_error",
                step="configuration",
                message=(
                    "missing credentials: use --username/--password or "
                    "NEW_API_USERNAME/NEW_API_PASSWORD"
                ),
                details={"required": ["NEW_API_USERNAME", "NEW_API_PASSWORD"]},
            )
            result = AuthResult(success=False, message=detail.message, error=detail)
            self.last_auth_result = result
            return result

        try:
            login_data = self._login(
                username=resolved_username,
                password=resolved_password,
                twofa_code=resolved_twofa,
            )
            profile = self._fetch_user_self(int(login_data["id"]))
            result = AuthResult(
                success=True,
                message="authentication succeeded",
                login=login_data,
                profile=profile,
            )
            self.last_auth_result = result
            return result
        except NewAPIClientError as exc:
            result = AuthResult(success=False, message=exc.detail.message, error=exc.detail)
            self.last_auth_result = result
            return result
        except Exception as exc:  # pragma: no cover - last-resort safety net
            detail = ErrorDetail(
                type="unexpected_error",
                step="auth",
                message=str(exc),
                exception_type=type(exc).__name__,
            )
            result = AuthResult(success=False, message=detail.message, error=detail)
            self.last_auth_result = result
            return result

    def checkin(self) -> CheckinResult:
        user_id = self.session.headers.get("New-API-User")
        if not user_id:
            detail = ErrorDetail(
                type="configuration_error",
                step="checkin",
                message="checkin requires an authenticated session; call auth() first",
                details={"required": ["authenticated session", "New-API-User header"]},
            )
            return CheckinResult(success=False, message=detail.message, error=detail)

        try:
            response, payload = self._request_payload(
                "POST",
                "api/user/checkin",
                step="checkin",
                headers=self._build_checkin_headers(user_id),
            )
        except NewAPIClientError as exc:
            return CheckinResult(success=False, message=exc.detail.message, error=exc.detail)
        except Exception as exc:  # pragma: no cover - last-resort safety net
            detail = ErrorDetail(
                type="unexpected_error",
                step="checkin",
                message=str(exc),
                exception_type=type(exc).__name__,
            )
            return CheckinResult(success=False, message=detail.message, error=detail)

        message = str(payload.get("message") or "")
        if payload.get("success") is True:
            return CheckinResult(
                success=True,
                message=message or "check-in succeeded",
                payload=payload,
            )

        if message == "今日已签到":
            return CheckinResult(
                success=True,
                message=message,
                already_checked_in=True,
                payload=payload,
            )

        detail = self._detail_from_response(
            "api_error",
            "checkin",
            f"checkin failed: {message or 'unknown error'}",
            response=response,
            response_json=payload,
        )
        return CheckinResult(success=False, message=detail.message, payload=payload, error=detail)

    def fetch_optional(self, path: str) -> Any:
        _, data = self._request_data("GET", path, step=f"fetch {path}")
        return data

    def _login(
        self,
        *,
        username: str,
        password: str,
        twofa_code: str | None = None,
    ) -> dict[str, Any]:
        login_url = self._build_url("api/user/login")
        if self.turnstile_token:
            login_url = f"{login_url}?turnstile={self.turnstile_token}"

        response, data = self._request_data(
            "POST",
            login_url,
            step="login",
            absolute_url=True,
            json={"username": username, "password": password},
        )

        if data.get("require_2fa"):
            if not twofa_code:
                raise NewAPIClientError(
                    self._detail_from_response(
                        "configuration_error",
                        "2FA verification",
                        "account requires 2FA; pass --twofa-code or NEW_API_2FA_CODE",
                        response=response,
                        response_json={"success": True, "data": data},
                        details={"require_2fa": True},
                    )
                )

            response, data = self._request_data(
                "POST",
                "api/user/login/2fa",
                step="2FA verification",
                json={"code": twofa_code},
            )

        self._validate_login_data(data, response=response)
        return data

    def _fetch_user_self(self, user_id: int) -> dict[str, Any]:
        self.session.headers["New-API-User"] = str(user_id)
        _, data = self._request_data("GET", "api/user/self", step="fetch user profile")
        return data

    def _request_data(
        self,
        method: str,
        path_or_url: str,
        *,
        step: str,
        absolute_url: bool = False,
        **kwargs: Any,
    ) -> tuple[requests.Response, dict[str, Any]]:
        response, payload = self._request_payload(
            method,
            path_or_url,
            step=step,
            absolute_url=absolute_url,
            **kwargs,
        )
        data = self._require_success(response, payload, step)
        return response, data

    def _request_payload(
        self,
        method: str,
        path_or_url: str,
        *,
        step: str,
        absolute_url: bool = False,
        **kwargs: Any,
    ) -> tuple[requests.Response, dict[str, Any]]:
        url = path_or_url if absolute_url else self._build_url(path_or_url)

        try:
            response = self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            raise NewAPIClientError(
                self._network_error(step, exc, method=method, url=url)
            ) from exc

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise NewAPIClientError(self._http_error(step, response, exc)) from exc

        payload = self._decode_json(response, step)
        return response, payload

    def _decode_json(self, response: requests.Response, step: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise NewAPIClientError(
                self._detail_from_response(
                    "invalid_json",
                    step,
                    f"{step} returned non-JSON response",
                    response=response,
                    exception=exc,
                )
            ) from exc

        if not isinstance(payload, dict):
            raise NewAPIClientError(
                self._detail_from_response(
                    "invalid_json",
                    step,
                    f"{step} returned JSON that is not an object",
                    response=response,
                    response_json=payload,
                )
            )

        return payload

    def _require_success(
        self,
        response: requests.Response,
        payload: dict[str, Any],
        step: str,
    ) -> dict[str, Any]:
        if not payload.get("success"):
            message = payload.get("message") or "unknown error"
            raise NewAPIClientError(
                self._detail_from_response(
                    "api_error",
                    step,
                    f"{step} failed: {message}",
                    response=response,
                    response_json=payload,
                )
            )

        data = payload.get("data")
        if data is None:
            raise NewAPIClientError(
                self._detail_from_response(
                    "invalid_payload",
                    step,
                    f"{step} returned no data",
                    response=response,
                    response_json=payload,
                )
            )

        return data

    def _validate_login_data(self, data: dict[str, Any], *, response: requests.Response) -> None:
        required_keys = {"id", "username", "display_name", "group", "role", "status"}
        missing = sorted(required_keys - data.keys())
        if missing:
            raise NewAPIClientError(
                self._detail_from_response(
                    "invalid_payload",
                    "login",
                    f"login response missing keys: {', '.join(missing)}",
                    response=response,
                    response_json={"success": True, "data": data},
                    details={"missing_keys": missing},
                )
            )

    def _network_error(
        self,
        step: str,
        exc: requests.RequestException,
        *,
        method: str,
        url: str,
    ) -> ErrorDetail:
        request = getattr(exc, "request", None)
        return ErrorDetail(
            type="network_error",
            step=step,
            message=str(exc),
            exception_type=type(exc).__name__,
            method=getattr(request, "method", None) or method,
            url=getattr(request, "url", None) or url,
        )

    def _http_error(
        self,
        step: str,
        response: requests.Response,
        exc: requests.HTTPError,
    ) -> ErrorDetail:
        reason = response.reason or "HTTP error"
        response_json = self._try_response_json(response)
        return self._detail_from_response(
            "http_error",
            step,
            f"{step} failed with HTTP {response.status_code} {reason}",
            response=response,
            exception=exc,
            response_json=response_json,
        )

    def _detail_from_response(
        self,
        error_type: str,
        step: str,
        message: str,
        *,
        response: requests.Response,
        exception: Exception | None = None,
        response_json: Any | None = None,
        details: Any | None = None,
    ) -> ErrorDetail:
        request = getattr(response, "request", None)
        body_excerpt = (response.text or "")[:MAX_ERROR_BODY] or None
        return ErrorDetail(
            type=error_type,
            step=step,
            message=message,
            exception_type=type(exception).__name__ if exception is not None else None,
            method=getattr(request, "method", None),
            url=response.url,
            status_code=response.status_code,
            response_json=response_json,
            response_body_excerpt=body_excerpt,
            details=details,
        )

    def _try_response_json(self, response: requests.Response) -> Any | None:
        try:
            return response.json()
        except ValueError:
            return None

    def _build_url(self, path: str) -> str:
        return urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))

    def _build_checkin_headers(self, user_id: str) -> dict[str, str]:
        return {
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": self.base_url,
            "Referer": self._build_url("console/personal"),
            "New-API-User": str(user_id),
        }

    @staticmethod
    def _build_session(timeout: int) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "newapi/1.0",
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


if __name__ == "__main__":
    ANSI_RESET = "\033[0m"
    ANSI_BOLD = "\033[1m"
    ANSI_RED = "\033[31m"
    ANSI_GREEN = "\033[32m"
    ANSI_YELLOW = "\033[33m"
    ANSI_BLUE = "\033[34m"
    ANSI_CYAN = "\033[36m"

    def parse_args() -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description="Log in to a New API deployment, optionally run daily check-in, and fetch user profile data.",
        )
        parser.add_argument(
            "--base-url",
            default=os.getenv("NEW_API_BASE_URL"),
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
            "--checkin",
            action="store_true",
            help="Run daily check-in after successful login.",
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

    def use_color(stream) -> bool:
        return (
            hasattr(stream, "isatty")
            and stream.isatty()
            and os.getenv("NO_COLOR") is None
            and os.getenv("TERM") != "dumb"
        )

    def style(text: str, *codes: str, stream) -> str:
        if not use_color(stream) or not codes:
            return text
        return "".join(codes) + text + ANSI_RESET

    def format_value(value: Any) -> str:
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, float):
            return f"{value:,.2f}"
        if isinstance(value, bool):
            return "yes" if value else "no"
        if value is None:
            return "-"
        return str(value)

    def render_pairs(
        pairs: list[tuple[str, Any]],
        *,
        stream,
        indent: str = "  ",
    ) -> str:
        if not pairs:
            return ""
        width = max(len(label) for label, _ in pairs)
        lines = []
        for label, value in pairs:
            name = style(f"{label:<{width}}", ANSI_BOLD, ANSI_CYAN, stream=stream)
            lines.append(f"{indent}{name} : {format_value(value)}")
        return "\n".join(lines)

    def render_json_block(title: str, payload: Any, *, stream) -> str:
        heading = style(title, ANSI_BOLD, ANSI_BLUE, stream=stream)
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        indented = "\n".join(f"    {line}" for line in body.splitlines())
        return f"{heading}\n{indented}"

    def build_user_summary(auth_result: AuthResult) -> list[tuple[str, Any]]:
        login = auth_result.login or {}
        profile = auth_result.profile or {}
        summary_pairs: list[tuple[str, Any]] = []
        for label, key in (
            ("User ID", "id"),
            ("Username", "username"),
            ("Display Name", "display_name"),
            ("Group", "group"),
            ("Role", "role"),
            ("Status", "status"),
            ("Email", "email"),
            ("Quota", "quota"),
            ("Used Quota", "used_quota"),
            ("Requests", "request_count"),
        ):
            value = profile.get(key)
            if value in (None, ""):
                value = login.get(key)
            if value not in (None, ""):
                summary_pairs.append((label, value))
        return summary_pairs

    def print_success(
        auth_result: AuthResult,
        *,
        base_url: str,
        checkin_result: CheckinResult | None = None,
        extra_results: dict[str, Any] | None = None,
        stream=sys.stdout,
    ) -> None:
        header = style("[OK]", ANSI_BOLD, ANSI_GREEN, stream=stream)
        summary = style(auth_result.message, ANSI_BOLD, stream=stream)
        print(f"{header} {summary}", file=stream)
        print(
            render_pairs(
                [("Deployment", base_url)] + build_user_summary(auth_result),
                stream=stream,
            ),
            file=stream,
        )
        if checkin_result is not None:
            print("", file=stream)
            print(style("Check-In", ANSI_BOLD, ANSI_YELLOW, stream=stream), file=stream)
            checkin_status = (
                "already checked in today"
                if checkin_result.already_checked_in
                else "check-in completed"
            )
            print(
                render_pairs(
                    [
                        ("Status", checkin_status),
                        ("Message", checkin_result.message or "-"),
                    ],
                    stream=stream,
                ),
                file=stream,
            )
            payload_data = (
                checkin_result.payload.get("data")
                if isinstance(checkin_result.payload, dict)
                else None
            )
            if payload_data not in (None, "", {}, []):
                print("", file=stream)
                print(render_json_block("Check-In Payload", payload_data, stream=stream), file=stream)
        if extra_results:
            for title, payload in extra_results.items():
                print("", file=stream)
                print(
                    render_json_block(title.replace("_", " ").title(), payload, stream=stream),
                    file=stream,
                )

    def print_failure(
        detail: ErrorDetail,
        *,
        auth_result: AuthResult | None = None,
        stream=sys.stderr,
    ) -> None:
        header = style("[FAIL]", ANSI_BOLD, ANSI_RED, stream=stream)
        summary = style(detail.message, ANSI_BOLD, stream=stream)
        print(f"{header} {summary}", file=stream)

        pairs: list[tuple[str, Any]] = [
            ("Step", detail.step),
            ("Error Type", detail.type),
        ]
        if detail.method:
            pairs.append(("Method", detail.method))
        if detail.url:
            pairs.append(("URL", detail.url))
        if detail.status_code is not None:
            pairs.append(("HTTP Status", detail.status_code))
        if detail.exception_type:
            pairs.append(("Exception", detail.exception_type))
        print(render_pairs(pairs, stream=stream), file=stream)

        if auth_result is not None and auth_result.success:
            user_pairs = build_user_summary(auth_result)
            if user_pairs:
                print("", file=stream)
                print(style("Authenticated User", ANSI_BOLD, ANSI_YELLOW, stream=stream), file=stream)
                print(render_pairs(user_pairs, stream=stream), file=stream)

        if detail.details is not None:
            print("", file=stream)
            print(render_json_block("Error Details", detail.details, stream=stream), file=stream)
        if detail.response_json is not None:
            print("", file=stream)
            print(render_json_block("Server JSON", detail.response_json, stream=stream), file=stream)
        if detail.response_body_excerpt:
            print("", file=stream)
            title = style("Response Excerpt", ANSI_BOLD, ANSI_BLUE, stream=stream)
            body = "\n".join(f"    {line}" for line in detail.response_body_excerpt.splitlines())
            print(f"{title}\n{body}", file=stream)

    def run_cli() -> int:
        args = parse_args()
        client = Client(
            base_url=args.base_url,
            timeout=args.timeout,
            turnstile_token=args.turnstile_token,
        )

        auth_result = client.auth(
            args.username,
            args.password,
            twofa_code=args.twofa_code,
        )
        if not auth_result.success:
            detail = auth_result.error or ErrorDetail(
                type="auth_error",
                step="auth",
                message=auth_result.message,
            )
            print_failure(detail, auth_result=auth_result)
            return 1

        try:
            checkin_result: CheckinResult | None = None
            if args.checkin:
                checkin_result = client.checkin()
                if not checkin_result.success:
                    detail = checkin_result.error or ErrorDetail(
                        type="checkin_error",
                        step="checkin",
                        message=checkin_result.message,
                    )
                    print_failure(detail, auth_result=auth_result)
                    return 1

            extra_results: dict[str, Any] = {}
            if args.with_groups:
                extra_results["groups"] = client.fetch_optional("/api/user/self/groups")
            if args.with_models:
                extra_results["models"] = client.fetch_optional("/api/user/models")
            print_success(
                auth_result,
                base_url=client.base_url,
                checkin_result=checkin_result,
                extra_results=extra_results or None,
            )
            return 0
        except NewAPIClientError as exc:
            print_failure(exc.detail, auth_result=auth_result)
            return 1
        except Exception as exc:  # pragma: no cover - last-resort safety net
            detail = ErrorDetail(
                type="unexpected_error",
                step="post-auth",
                message=str(exc),
                exception_type=type(exc).__name__,
            )
            print_failure(detail, auth_result=auth_result)
            return 1

    raise SystemExit(run_cli())
