# Repository Guide

## Scope

This repository provides a single-file Python client and CLI for logging in to a generic `new-api` deployment and reading the authenticated user profile.

The main implementation lives in `new_api_requests_login.py`.

## Working Rules

- Preserve the external CLI contract unless the user explicitly asks to change it.
- Do not add third-party dependencies beyond what the repository already uses.
- Keep the main implementation in `new_api_requests_login.py` unless the user explicitly asks for a different layout.
- Keep the importable API usable for programmatic access, especially `Client` and `auth_result`-style workflows.
- Prefer terminal output that is concise, readable, and debug-friendly.

## Naming Rules

- Do not include any concrete site or deployment names in code, docs, examples, comments, commit-ready text, or user-facing output.
- Use `new-api` as the generic product/deployment name whenever a name is required.
- Keep example URLs, credentials, and descriptions generic and safe for open-source publication.

## Output Rules

- CLI output should be optimized for human reading first.
- Use ANSI colors and simple terminal styling only when supported by the terminal.
- On failure, include enough request and response detail to help both humans and LLMs debug the issue.
