from datetime import timedelta
from types import SimpleNamespace
from typing import cast

import pytest
from cbltest.api.database import Database
from cbltest.api.error import CblTestError
from cbltest.api.error_types import ErrorResponseBody
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorActivityLevel, ReplicatorProgress, ReplicatorStatus
from cbltest.responses import ServerVariant

STOPPED = ReplicatorActivityLevel.STOPPED
IDLE = ReplicatorActivityLevel.IDLE
BUSY = ReplicatorActivityLevel.BUSY
INTERVAL = timedelta(milliseconds=10)
TIMEOUT = timedelta(seconds=1)


def status(activity: ReplicatorActivityLevel, code: int | None = None, message: str = "") -> ReplicatorStatus:
    error = None if code is None else ErrorResponseBody("CBL", code, message)
    return ReplicatorStatus(ReplicatorProgress({"completed": False}), activity, error)


def replicator(
    monkeypatch: pytest.MonkeyPatch, *statuses: ReplicatorStatus
) -> tuple[Replicator, list[ReplicatorStatus]]:
    """A Replicator whose get_status returns `statuses` in order, then repeats the last one.
    Also returns the list of statuses that get_status returned."""
    factory = SimpleNamespace(variant=lambda index: ServerVariant.C)
    db = cast(Database, SimpleNamespace(_index=0, _request_factory=factory, name="db1"))
    r = Replicator(db, "ws://sg:4984/travel")
    seen: list[ReplicatorStatus] = []

    async def get_status() -> ReplicatorStatus:
        seen.append(statuses[min(len(seen), len(statuses) - 1)])
        return seen[-1]

    monkeypatch.setattr(r, "get_status", get_status)
    return r, seen


@pytest.mark.asyncio
async def test_wait_for_polls_until_activity(monkeypatch: pytest.MonkeyPatch) -> None:
    r, seen = replicator(monkeypatch, status(BUSY), status(BUSY), status(IDLE))
    assert (await r.wait_for(IDLE, interval=INTERVAL, timeout=TIMEOUT)).activity == IDLE
    assert len(seen) == 3


@pytest.mark.asyncio
async def test_wait_for_rejects_error(monkeypatch: pytest.MonkeyPatch) -> None:
    r, _ = replicator(monkeypatch, status(STOPPED, 10403, "forbidden"))
    with pytest.raises(AssertionError, match=r"reached STOPPED, error: \(CBL / 10403\) forbidden"):
        await r.wait_for(STOPPED, interval=INTERVAL, timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_wait_for_times_out_with_last_status(monkeypatch: pytest.MonkeyPatch) -> None:
    r, _ = replicator(monkeypatch, status(BUSY))
    with pytest.raises(TimeoutError, match="is BUSY, not IDLE"):
        await r.wait_for(IDLE, interval=INTERVAL, timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_wait_for_stops_at_once_on_stopped_with_error(monkeypatch: pytest.MonkeyPatch) -> None:
    r, seen = replicator(monkeypatch, status(BUSY), status(STOPPED, 10401, "unauthorized"))
    with pytest.raises(CblTestError, match="stopped while waiting for IDLE, error: .*10401"):
        await r.wait_for(IDLE, interval=INTERVAL, timeout=timedelta(seconds=30))
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_wait_for_keeps_waiting_on_stopped_without_error(monkeypatch: pytest.MonkeyPatch) -> None:
    r, _ = replicator(monkeypatch, status(STOPPED), status(IDLE))
    assert (await r.wait_for(IDLE, interval=INTERVAL, timeout=TIMEOUT)).activity == IDLE


@pytest.mark.asyncio
async def test_wait_for_error_accepts_matching_error(monkeypatch: pytest.MonkeyPatch) -> None:
    r, _ = replicator(monkeypatch, status(BUSY), status(STOPPED, 10403, "No accessible collections for sync"))
    result = await r.wait_for_error(code=10403, message="accessible collections", interval=INTERVAL, timeout=TIMEOUT)
    assert result.error is not None and result.error.code == 10403


@pytest.mark.parametrize(
    ("code", "message", "expected"),
    [
        (None, None, "without the expected error"),
        (10401, None, "expected code 10401"),
        (None, "other", "expected a message containing 'other'"),
        (10403, "other", "expected code 10403 and a message containing 'other'"),
    ],
)
@pytest.mark.asyncio
async def test_wait_for_error_rejects_missing_or_mismatched_error(
    monkeypatch: pytest.MonkeyPatch, code: int | None, message: str | None, expected: str
) -> None:
    error_code = None if expected == "without the expected error" else 10403
    r, _ = replicator(monkeypatch, status(STOPPED, error_code, "forbidden"))
    with pytest.raises(AssertionError, match=expected):
        await r.wait_for_error(code=code, message=message, interval=INTERVAL, timeout=TIMEOUT)
