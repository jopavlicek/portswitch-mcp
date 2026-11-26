# CLAUDE.md — PortSwitch Agent Instructions

## Resolving Docker Port Conflicts (PortSwitch Workflow)

When starting a project fails with a port collision (`port is already allocated`, `address already in use`), or before running `docker compose up`:

1. **Inspect first:** Call `check_conflicts(path)` with the absolute path of the project folder you are starting. Do **not** guess, run `lsof` to kill processes, or edit ports before checking.
2. **Explain clearly:** Tell the user which project folder and container hold the conflicting port, and follow the returned `advice` field (e.g., whether it is a sibling git worktree or holds database volumes).
3. **Choose one safe action:**
   - **Sibling git worktree / must stay running:** Do **not** stop the other project. Call `suggest_free_port(port)` and update **only the current project's** port configuration (e.g., `.env`). Never edit the other project's files.
   - **Forgotten/idle project:** Propose stopping it with `stop_project(path)` (non-destructive; keeps containers and volume data) and **wait for explicit user confirmation** before calling `stop_project`.
4. **Never run destructive Docker commands** (`docker compose down`, `down -v`, `docker rm`, `docker volume rm`, `docker system prune`) to free a port.

## Developing This Repository

See [`AGENTS.md`](AGENTS.md) for architecture, strict MVP scope, safety-by-design rules, and test commands (`uv run pytest`).
