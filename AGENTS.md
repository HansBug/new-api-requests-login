# Repository Guide

## Purpose

This repository contains a single-file Python client and CLI for logging in to a generic `new-api` deployment and reading the authenticated user profile.

The project is intentionally small and open-source-safe:

- one main Python implementation file
- no extra third-party dependencies beyond `requests`
- no concrete deployment names in code or docs
- a CLI entrypoint and an importable client API living in the same file

## Repository Structure

Current top-level layout:

- `new_api_requests_login.py`
  Main implementation. This file contains the importable client, result/error models, request handling, and the CLI code under `if __name__ == "__main__":`.
- `README.md`
  Public-facing usage documentation.
- `AGENTS.md`
  Repository-specific engineering and collaboration guide.
- `requirements.txt`
  Runtime dependency list. Keep this minimal.
- `.gitignore`
  Ignore rules for local environments, editor state, caches, and secret files.
- `.env.example`
  Safe example shell exports for local usage.
- `.env`
  Local-only credentials and configuration. Never commit real values.
- `venv/`
  Local development environment. Not part of the product surface.
- `__pycache__/`
  Python cache artifacts. Ignore for implementation decisions.

## Architecture Overview

The codebase is intentionally split into two logical layers inside `new_api_requests_login.py`:

1. Importable core layer
   This is everything above `if __name__ == "__main__":`.
   It must remain usable from other Python code via imports.

2. CLI layer
   This is everything inside `if __name__ == "__main__":`.
   It owns argument parsing, ANSI styling, human-readable rendering, and process exit codes.

This separation is important. Changes to the CLI should not break programmatic use of `Client`, and changes to client internals should not force CLI-specific concerns into the importable API.

## Core Types

### `ErrorDetail`

`ErrorDetail` is the canonical structured error payload.

It captures:

- logical error type
- failed step
- human-readable message
- exception type when available
- HTTP method and URL
- HTTP status code
- parsed JSON response when available
- raw response excerpt for debugging
- structured extra details

If error reporting needs to become richer, extend `ErrorDetail` first instead of inventing parallel error formats.

### `NewAPIClientError`

`NewAPIClientError` is the internal exception wrapper used inside the client layer.

Rule:

- internal request helpers may raise `NewAPIClientError`
- public `Client.auth(...)` should convert those exceptions into `AuthResult(success=False, ...)`

This keeps the importable API predictable.

### `AuthResult`

`AuthResult` is the public result model for authentication.

Expected shape:

- `success`
- `message`
- `login`
- `profile`
- `error`

External code should be able to do:

```python
client = Client()
auth_result = client.auth(username, password)
if auth_result.success:
    ...
else:
    ...
```

Do not change this workflow unless explicitly requested.

## `Client` Architecture

`Client` is the only network-facing abstraction and should remain the main programmatic entrypoint.

### Constructor Responsibilities

`Client(...)` currently owns:

- base URL resolution
- timeout configuration
- optional turnstile token handling
- `requests.Session` creation
- shared request headers

It may read environment variables for defaults, but it must not read `.env` files directly. Environment loading belongs to the shell, not this script.

### Public Methods

Current public surface:

- `auth(...)`
- `fetch_optional(...)`

Keep this surface small and coherent.

If more functionality is added later, prefer adding methods to `Client` rather than scattering free functions around the module.

### Internal Flow

Authentication currently follows this sequence:

1. Validate required runtime configuration.
2. POST to `api/user/login`.
3. If required, POST to `api/user/login/2fa`.
4. Validate the login response payload shape.
5. Set `New-API-User` on the session.
6. GET `api/user/self`.
7. Return a structured `AuthResult`.

All network request execution is funneled through `_request_data(...)`.

This is an important invariant. If new endpoints are added, prefer reusing the existing helper stack:

- `_request_data(...)`
- `_decode_json(...)`
- `_require_success(...)`
- `_detail_from_response(...)`

That keeps error behavior uniform.

## CLI Architecture

Everything CLI-specific must remain inside `if __name__ == "__main__":`.

This includes:

- `argparse` setup
- ANSI color constants
- terminal capability detection
- pretty-print helpers
- CLI success and failure rendering
- process exit code handling

Do not move CLI helpers back to module top-level unless explicitly required.

### CLI Output Design

The CLI is optimized for humans first.

Success output should:

- clearly mark success
- show the deployment target
- show a concise user summary
- avoid dumping the full raw profile by default

Failure output should:

- clearly mark failure
- identify the failed step
- include request metadata when available
- include server JSON when available
- include a response excerpt when useful

Color and styling rules:

- use ANSI codes only
- enable colors only when the terminal supports them
- honor `NO_COLOR`
- do not require rich terminal libraries

## Compatibility Rules

Unless the user explicitly asks for a breaking change, preserve all of the following:

- script filename: `new_api_requests_login.py`
- environment variable names: `NEW_API_BASE_URL`, `NEW_API_USERNAME`, `NEW_API_PASSWORD`, `NEW_API_2FA_CODE`, `NEW_API_TURNSTILE_TOKEN`
- CLI flags and their meanings
- exit code behavior
- `Client().auth(...)` result-driven usage pattern
- no automatic `.env` file parsing inside Python
- no new non-stdlib dependencies beyond `requests`

## Naming Rules

Open-source-safe naming is a hard requirement in this repository.

- Do not include concrete deployment names in code, docs, comments, examples, commit-ready text, or user-facing output.
- Always use `new-api` as the generic deployment/product name when a name is required.
- Keep URLs, credentials, and examples generic.
- If older deployment-specific wording appears anywhere, remove or generalize it instead of preserving it.

## Change Strategy

When changing this repository:

- prefer editing the existing file instead of creating new modules
- preserve the single-file architecture unless the user explicitly requests a restructuring
- keep the importable layer and CLI layer clearly separated
- avoid broad rewrites that alter public behavior without a concrete reason
- verify both programmatic and CLI use cases after changes

## Verification Expectations

For meaningful changes, verify both of these paths when possible:

1. Import path
   Example: import `Client`, call `client.auth(...)`, inspect `AuthResult`

2. CLI path
   Example: run `python new_api_requests_login.py` with exported environment variables

When validating failures, prefer confirming that:

- the command exits non-zero
- the failed step is visible
- debug metadata is present
- the output remains readable

## Secrets and Local State

- Never commit real credentials.
- Treat `.env` as local-only.
- Keep `.env.example` sanitized and generic.
- Ignore `venv/`, `__pycache__/`, editor state, and other local artifacts unless the user explicitly asks to work on them.
