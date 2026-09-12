# Repository Guidelines

## Project Structure & Module Organization

This repository implements **hola**, a phone-conversation prototype for older adults.

- `compose.yaml` defines the local LiveKit, SIP, Redis, and Python services.
- `hola/agent.py` handles conversations; `call_recording.py` stores audio and transcripts.
- `hola/context-api/` contains the FastAPI/SQLite profile and call API, tests, and shared prompt.
- `hola/web-chat/` contains the aiohttp server, browser UI (`index.html`), and tests.
- `hola/orange-proxy/` handles Orange SIP registration; configuration and provisioning scripts live directly under `hola/`.
- `benchmark.py` and `input.wav` support standalone GPT-Live benchmarking. `DOCS/PROJECT.md` describes the broader product vision; service READMEs document implemented behavior.

## Build, Test, and Development Commands

Run commands from the repository root:

- `python3 hola/configure.py`: create missing root `.env` settings interactively; requires Python 3.10+.
- `docker compose config --quiet`: validate configuration after setup.
- `docker compose up -d --build`: build and start the stack; web chat is at `http://localhost:8092`.
- `docker compose ps -a`: inspect services; `sip-setup` exiting with code 0 is expected.
- `docker compose down`: stop services while preserving stored data.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/variables, `PascalCase` classes, and uppercase configuration constants. Follow adjacent code's quoting and layout. Keep service dependencies in their respective `requirements.txt` files. No formatter or linter is configured; avoid unrelated formatting changes.

## Testing Guidelines

Use Python 3.12 and the `.venv-livekit` setup in `hola/README.md`. Tests use `unittest`, async test cases, mocks, and temporary storage; no coverage threshold is configured.

```sh
.venv-livekit/bin/python -m unittest discover -s hola -p test_configure.py -v
.venv-livekit/bin/python -m unittest discover -s hola/context-api -p 'test_*.py' -v
.venv-livekit/bin/python -m unittest discover -s hola/web-chat -p 'test_*.py' -v
```

Name tests `test_*.py` and methods `test_<behavior>`. Cover changed behavior and failure paths. Distinguish mocked checks from browser/audio and real carrier-call verification.

## Commit & Pull Request Guidelines

Work on a focused `codex/<ticket>-<slug>` branch from current `main`. History uses imperative subjects, e.g. “Move web chat interface into hola/web-chat”. PRs should explain behavior changes, link relevant issues, report validation and limitations, and include screenshots for UI changes. Update affected READMEs.

## Security & Configuration

Never commit credentials, profiles, or recordings. Preserve distinct API tokens and loopback-only administrative endpoints. `docker compose down -v` deletes persistent data; avoid it during routine development.
