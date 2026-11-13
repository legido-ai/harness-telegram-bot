# Verification — 003-unified-backend

Date: 2026-11-13. Commit deployed: `771a4af` plus the entrypoint HOME guard.
Image: `ghcr.io/legido-ai/harness-telegram-bot:sha-local` (`3e95f2610616`, arm64,
634 MB), built locally from this branch because the CI run could not be
confirmed (see gaps).

## What was checked

**Offline suite**

- `pytest -q` → **175 passed** (was 163 before the new backend work), no network,
  no credentials. Fake OpenCode server and a fake `pi --mode rpc` process.
- `ruff check app tests` → clean.
- `python -m compileall app tests` → clean.

**Configuration**

- `BACKEND=opencode` with `OPENCODE_SERVER_PASSWORD` → backend `opencode`.
- `BACKEND=pi` without any OpenCode variable → backend `pi`,
  `supports_agents=False`, `supports_permissions=False`, sessions at
  `/data/sessions`.
- `BACKEND=nope` → `ConfigError: BACKEND must be one of: opencode, pi`.
- `BACKEND=opencode` without a password → `ConfigError: missing required
  configuration: OPENCODE_SERVER_PASSWORD`.

**Deployment on oci2**

| Container | Image | Backend | Result |
|---|---|---|---|
| `opencode2-telegram-bot` | `harness-telegram-bot:sha-local` | `opencode` | healthy, poller alive, agent reachable |
| `pi` | `harness-telegram-bot:sha-local` | `pi` | healthy, poller alive, agent reachable |

- `/healthz` payloads: `{'status': 'ok', 'backend': 'opencode'|'pi',
  'poller_alive': True, 'agent_ok': True}`.
- Pi container runs as uid 10001, keeps `pi-data` and `pi-workspace` ownership,
  found 11 session files in `/data/sessions` and wrote
  `/home/appuser/.pi/agent/models.json` from the environment.
- Pi RPC smoke test inside the container, exactly as the backend spawns it:
  `get_state` returned `sessionFile`, model `deepseek-v4.1-flash` with
  `contextWindow: 262144`, no LLM call, session file created and removed.
- Both containers reached `https://api.telegram.org` (HTTP 200) and logged no
  errors after a transient network blip during the recreate.

**Data continuity**

- The OpenCode database was kept (`opencode2-telegram-bot-data`), so sessions,
  bindings, pinned cards and TTS modes survive; `bind_backend('opencode')` wrote
  the new `meta` row without clearing anything.
- Pi keeps its session files; the bridge database is new, so conversations start
  unbound until the first message (expected).

## Rollback

Previous images are tagged and present on the host:

- `rollback-opencode2-bot:0.2.1` (`b9e6bca0127e`)
- `rollback-pi:0.3.0-before` and `pi:rollback-640705b` (`640705bf8e0d`)

Recreate either container from those tags with the same env and volumes; no
schema downgrade is needed because the OpenCode schema did not change.

## Gaps

1. **CI image unconfirmed.** The App used for pushes cannot read the Actions API
   (`403`), so the workflow run for `771a4af` could not be inspected and no
   `ghcr.io/…:sha-*` image appeared within ~12 minutes. The deployed image is the
   local arm64 build of the same commit. The workflow itself is in place and
   publishes `latest`, version and `sha-<commit>` on the next push to `main`.
2. **Compose `up` is blocked by an unrelated schema error.** Both available
   compose binaries reject `services.*.mem_swap` in
   `agentic-architecture/box/compose.yml` (`false schema`), so both containers
   were recreated with `docker run` using the previous container's exact env,
   volumes, network and restart policy. The compose file still carries the
   intended `BACKEND: pi` and the new `PI_BOT_BASE`; it needs a compose version
   that understands `mem_swap` (or those keys removed) before the next
   `compose up`.
3. **No live chat turn.** Verification stopped at health, configuration and RPC
   spawn; a real message in each chat is the operator's test. The Pi adapter's
   full turn is covered offline by the fake RPC process and the contract test.
4. **Pi has no Docker CLI in the running container**, exactly as before this
   change (`docker: not found`, socket not readable by uid 10001). The box-side
   `pi/Dockerfile` that adds the CLI was rebuilt as `pi:current` but the
   container was recreated from the base image to match the previous behaviour.

## Reproduce

```bash
cd /workspace/harness-telegram-bot
make test                      # 175 offline tests
docker build -t harness:local .
docker run --rm --entrypoint python harness:local -c \
  "from app.config import Settings; print(Settings.from_env({'BACKEND':'pi','TELEGRAM_BOT_TOKEN':'1:x','TELEGRAM_ALLOWED_USER_IDS':'1'}).backend)"
```
