from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest


async def wait_for(predicate: Callable[[], bool], timeout: float = 3.0, step: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(step)
    raise AssertionError("condition not met within timeout")


@pytest.fixture
async def settle() -> None:
    await asyncio.sleep(0)
