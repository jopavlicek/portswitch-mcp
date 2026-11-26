# AGENTS.md — PortSwitch MCP Development Guide

This file defines repository conventions, commands, and non-negotiable safety rules for AI coding agents working on **PortSwitch MCP**.

## Project Overview & Strict MVP Scope

PortSwitch is a lightweight, safety-first Python MCP server (`mcp[cli]>=2.3,<3`) using Docker CLI JSON output to help AI coding agents resolve Docker Compose port collisions without destructive commands.

**MVP surface (do not expand without explicit approval):**
1. **3 MCP tools** in `src/portswitch/server.py`:
   - `check_conflicts(path)` — read-only; resolves `port -> container -> project_folder`, git worktree relationship, volumes/mounts, and safety advice.
   - `suggest_free_port(port)` — read-only; returns the nearest free host port.
   - `stop_project(path)` — non-destructive `docker stop <container_ids>`; requires user confirmation and only stops compose projects previously identified by `check_conflicts`.
2. **Agent instructions** in `CLAUDE.md` (and `examples/claude-settings.json`).
3. **Evaluation suite** in `scenarios/` (S1: two projects on `5432`, S2: two git worktrees on `3000`/`5432`, S3: conflicting stack with DB data in an anonymous volume).

**Out of scope:** non-Docker process killing, web UI, container/volume deletion, or extra MCP tools.

## Safety-by-Design Rules (Non-Negotiable)

- **No destructive Docker commands in code:** Never add `docker compose down`, `down -v`, `docker rm`, `docker volume rm`, or any `prune` command to `src/portswitch/`. The only mutating Docker command allowed is `docker stop <container_ids>`.
- **Identified-project gate:** `stop_project(path)` must only stop compose projects explicitly identified as conflicts by `check_conflicts(path)` in the current session.
- **MCP stdio hygiene:** The server communicates over `stdin`/`stdout`. **Never use `print()`** in `src/portswitch/`; always log to `stderr` via Python's `logging` module.
- **Read-only context:** Never modify reference materials outside this repository (e.g., the read-only context folder).
- **Never edit scenario templates during runs:** `scenarios/*/template/` are immutable fixtures; runtime state belongs only in the git-ignored `scenarios/.work/`.

## Repository Layout

```text
src/portswitch/
  server.py          # Production MCP server (registered in .mcp.json)
  debug_server.py    # Debug entrypoint exposing internal helpers (MCP Inspector only)
tests/               # Pytest unit tests with mocked Docker CLI / git / socket calls
examples/
  claude-settings.json  # Recommended Claude Code allow/ask/deny permission rules
scenarios/
  _shared/           # Shared bash helpers (lib.sh) and health server (health.py)
  s1-two-projects/   # Scenario 1: two compose projects colliding on 5432
  s2-worktrees/      # Scenario 2: two git worktrees colliding on 3000 & 5432
  s3-data-volume/    # Scenario 3: conflicting stack with anonymous DB volume
```

## Common Commands

- **Install dependencies (Python 3.12 via `uv`):**
  ```bash
  uv sync
  ```
- **Run unit tests:**
  ```bash
  uv run pytest
  ```
- **Inspect server interactively (MCP Inspector):**
  ```bash
  uv run mcp dev src/portswitch/server.py
  uv run mcp dev src/portswitch/debug_server.py
  ```
- **Run a scenario lifecycle (macOS/Linux/Git Bash with Docker running):**
  ```bash
  scenarios/s1-two-projects/setup.sh
  scenarios/s1-two-projects/check.sh
  scenarios/s1-two-projects/reset.sh
  ```

## Git & Code Conventions

- Python `>=3.10` (pinned to `3.12` in `.python-version`), standard library + `mcp` SDK only for runtime dependencies.
- Keep tool responses as clean JSON-serializable `dict`s; return structured `{"error": ...}` dicts instead of crashing on Docker or filesystem errors.
- Work in small, logical commits. Every change to `src/portswitch/server.py` must be accompanied by unit tests in `tests/`.
