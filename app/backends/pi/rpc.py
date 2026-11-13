"""JSONL transport for ``pi --mode rpc``.

One child process per session file. The process owns the conversation; this
module only writes commands and demultiplexes what comes back: responses are
matched to their pending future by ``id``, everything else (message deltas,
lifecycle events, extension UI requests) goes to an event queue that the
backend drains during a run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.backends.errors import Busy, HarnessError, Unavailable

log = logging.getLogger("bot.backend.pi.rpc")

UI_DIALOGS = {"select", "confirm", "input", "editor"}


class PiProcessError(HarnessError):
    pass


@dataclass
class PiProcess:
    proc: asyncio.subprocess.Process
    session: Path | None
    pending: dict[str, asyncio.Future] = field(default_factory=dict)
    events: asyncio.Queue = field(default_factory=asyncio.Queue)
    counter: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    reader: asyncio.Task | None = None
    stderr: asyncio.Task | None = None
    last_used: float = field(default_factory=time.monotonic)
    dead: bool = False


class PiRpc:
    def __init__(
        self,
        *,
        binary: str,
        provider: str,
        model: str,
        session_dir: Path,
        workspace: Path,
        thinking: str = "",
        extra_args: tuple[str, ...] = (),
        system_prompt: str = "/app/telegram-prompt.md",
        command_timeout: float = 60.0,
    ) -> None:
        self.binary = binary
        self.provider = provider
        self.model = model
        self.session_dir = session_dir
        self.workspace = workspace
        self.thinking = thinking
        self.extra_args = tuple(extra_args)
        self.system_prompt = system_prompt
        self.command_timeout = command_timeout
        self._has_system_prompt = Path(self.system_prompt).exists()

    # -- process lifecycle ------------------------------------------------

    async def spawn(self, session: Path | None = None) -> PiProcess:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        args = [
            self.binary,
            "--mode",
            "rpc",
            "--provider",
            self.provider,
            "--model",
            self.model,
            "--session-dir",
            str(self.session_dir),
        ]
        if self.thinking:
            args += ["--thinking", self.thinking]
        if session is not None:
            args += ["--session", str(session)]
        args += list(self.extra_args)
        if self._has_system_prompt:
            args += ["--append-system-prompt", self.system_prompt]

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
            )
        except FileNotFoundError as exc:
            raise Unavailable(f"the Pi binary ({self.binary}) is not installed") from exc
        except OSError as exc:
            raise Unavailable("the Pi process could not be started") from exc

        node = PiProcess(proc=proc, session=session)
        node.reader = asyncio.create_task(self._read(node), name=f"pi-reader:{id(node)}")
        node.stderr = asyncio.create_task(self._read_stderr(node), name=f"pi-stderr:{id(node)}")
        log.info("pi spawned", extra={"session": str(session) if session else "new"})
        return node

    async def close(self, node: PiProcess) -> None:
        node.dead = True
        for future in node.pending.values():
            if not future.done():
                future.set_exception(Unavailable("the Pi process stopped"))
        node.pending.clear()
        if node.proc.returncode is None:
            try:
                if node.proc.stdin:
                    node.proc.stdin.close()
            except (OSError, RuntimeError):
                pass
            node.proc.terminate()
            try:
                await asyncio.wait_for(node.proc.wait(), timeout=5)
            except TimeoutError:
                node.proc.kill()
        for task in (node.reader, node.stderr):
            if task and not task.done():
                task.cancel()
        log.info("pi closed", extra={"session": str(node.session) if node.session else "new"})

    # -- stdin/stdout -----------------------------------------------------

    async def command(
        self, node: PiProcess, payload: dict[str, Any], *, timeout: float | None = None  # noqa: ASYNC109
    ) -> dict[str, Any]:
        if node.dead or node.proc.returncode is not None:
            raise Unavailable("the Pi process is not running")
        if node.proc.stdin is None:
            raise Unavailable("the Pi process has no stdin")
        node.counter += 1
        request_id = str(node.counter)
        body = {**payload, "id": request_id}
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        node.pending[request_id] = future
        node.last_used = time.monotonic()
        try:
            node.proc.stdin.write((json.dumps(body) + "\n").encode())
            await node.proc.stdin.drain()
            return await asyncio.wait_for(future, timeout=timeout or self.command_timeout)
        except TimeoutError as exc:
            raise PiProcessError("the Pi process did not answer") from exc
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise Unavailable("the Pi process closed its input") from exc
        finally:
            node.pending.pop(request_id, None)

    async def _read(self, node: PiProcess) -> None:
        assert node.proc.stdout is not None
        buffer = b""
        try:
            while True:
                chunk = await node.proc.stdout.read(65536)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    if not raw.strip():
                        continue
                    try:
                        record = json.loads(raw.decode("utf-8", "replace"))
                    except json.JSONDecodeError:
                        log.warning("pi sent a non-JSON line")
                        continue
                    if isinstance(record, dict):
                        await self._dispatch(node, record)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("pi output reader stopped: %s", type(exc).__name__)
        finally:
            node.dead = True
            for future in node.pending.values():
                if not future.done():
                    future.set_exception(Unavailable("the Pi process exited"))
            node.pending.clear()

    async def _dispatch(self, node: PiProcess, record: dict[str, Any]) -> None:
        if record.get("type") == "response":
            future = node.pending.pop(str(record.get("id")), None)
            if future and not future.done():
                if record.get("success"):
                    data = record.get("data")
                    future.set_result(data if isinstance(data, dict) else {})
                else:
                    message = str(record.get("error") or "command failed")
                    if "stream" in message.lower() and "prompt" in record.get("command", ""):
                        future.set_exception(Busy())
                    else:
                        future.set_exception(PiProcessError(message))
            return

        if record.get("type") == "extension_ui_request":
            await self._dismiss_dialog(node, record)
            return

        node.events.put_nowait(record)

    async def _dismiss_dialog(self, node: PiProcess, record: dict[str, Any]) -> None:
        """A dialog nobody can press: cancel it so the agent never hangs.

        The cancel is written without waiting for its response: waiting here
        would deadlock, because the response arrives on the reader that is
        currently dispatching this record.
        """

        method = str(record.get("method") or "")
        if method in UI_DIALOGS and not node.dead and node.proc.stdin is not None:
            payload = {"type": "extension_ui_response", "id": record.get("id"), "cancelled": True}
            try:
                node.proc.stdin.write((json.dumps(payload) + "\n").encode())
                await node.proc.stdin.drain()
            except (OSError, RuntimeError):
                log.debug("pi dialog could not be cancelled")
        log.info("pi extension dialog dismissed", extra={"method": method})
        node.events.put_nowait({"type": "harness_ui_request", "method": method})

    async def _read_stderr(self, node: PiProcess) -> None:
        assert node.proc.stderr is not None
        try:
            while line := await node.proc.stderr.readline():
                log.debug("pi stderr: %s", line.decode("utf-8", "replace").rstrip())
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.debug("pi stderr reader stopped")
