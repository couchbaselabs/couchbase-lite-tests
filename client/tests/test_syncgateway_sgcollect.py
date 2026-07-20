"""Unit tests for SGCollect helpers on SyncGateway: start_sgcollect, run_sgcollect,
and the multi-node run_sgcollects()."""

import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import ClientSession
from cbltest.api.error import CblTestError
from cbltest.api.jsonserializable import JSONSerializable
from cbltest.api.syncgateway import SGCollectRedactLevel, SyncGateway
from cbltest.plugins.sgcollect_fixture import run_sgcollects


class FakeSyncGateway(SyncGateway):
    """
    Test-only SyncGateway. Replaces only the network-touching primitives with
    plain in-memory state, so the real logic of start_sgcollect()/run_sgcollect()
    runs unmocked and is exercised by these tests.
    """

    def __init__(self, hostname: str = "sg.example.com") -> None:
        with (
            patch("cbltest.api.syncgateway.ClientSession", autospec=True),
            patch("cbltest.api.syncgateway.requests.get", autospec=True),
        ):
            super().__init__(url=hostname, username="user", password="pass")

        self.sent_requests: list[tuple[str, str, JSONSerializable | None]] = []
        self.send_request_result: Any = {"status": "started"}
        # Each run_sgcollect() call pops the next snapshot off the front, so
        # tests configure [before, after] (or more, for run_sgcollects()).
        self.caddy_snapshots: list[list[str]] = [[]]
        self.downloaded: list[tuple[str, str]] = []

    async def _send_request(
        self,
        method: str,
        path: str,
        payload: JSONSerializable | None = None,
        params: dict[str, str] | None = None,
        session: ClientSession | None = None,
    ) -> Any:
        self.sent_requests.append((method, path, payload))
        return self.send_request_result

    async def wait_for_sgcollect_to_complete(
        self, max_attempts: int = 60, wait_time: int = 2
    ) -> None:
        return None

    async def list_files_via_caddy(self, pattern: str | None = None) -> list[str]:
        return self.caddy_snapshots.pop(0)

    async def download_file_via_caddy(
        self, remote_filename: str, local_path: str
    ) -> None:
        self.downloaded.append((remote_filename, local_path))


class TestSGCollectRedactLevel:
    def test_values(self):
        assert SGCollectRedactLevel.NONE.value == "none"
        assert SGCollectRedactLevel.PARTIAL.value == "partial"
        assert SGCollectRedactLevel.FULL.value == "full"


class TestStartSGCollect:
    @pytest.mark.asyncio
    async def test_defaults_to_no_redaction(self):
        sg = FakeSyncGateway()
        resp = await sg.start_sgcollect()

        assert resp == {"status": "started"}
        method, path, payload = sg.sent_requests[-1]
        assert (method, path) == ("post", "/_sgcollect_info")
        assert payload is not None
        assert payload.to_json() == {"upload": False}

    @pytest.mark.asyncio
    async def test_passes_through_redact_options(self):
        sg = FakeSyncGateway()
        await sg.start_sgcollect(
            redact_level=SGCollectRedactLevel.PARTIAL,
            redact_salt="salt",
            output_dir="/home/ec2-user/log",
        )

        _, _, payload = sg.sent_requests[-1]
        assert payload is not None
        assert payload.to_json() == {
            "upload": False,
            "redact_level": "partial",
            "redact_salt": "salt",
            "output_dir": "/home/ec2-user/log",
        }


class TestRunSGCollect:
    @pytest.mark.asyncio
    async def test_downloads_the_single_new_zip(self, tmp_path: Path):
        sg = FakeSyncGateway()
        sg.caddy_snapshots = [[], ["sgcollectinfo-abc.zip"]]

        result = await sg.run_sgcollect(tmp_path)

        safe_host = sg.hostname.replace(".", "_")
        expected = tmp_path / f"{safe_host}-sgcollectinfo-abc.zip"
        assert result == expected
        assert sg.downloaded == [("sgcollectinfo-abc.zip", str(expected))]
        # start_sgcollect() ran for real, so confirm no redact level was sent by default.
        _, _, payload = sg.sent_requests[-1]
        assert payload is not None
        assert "redact_level" not in payload.to_json()

    @pytest.mark.asyncio
    async def test_ignores_zip_that_already_existed(self, tmp_path: Path):
        sg = FakeSyncGateway()
        sg.caddy_snapshots = [
            ["sgcollectinfo-old.zip"],
            ["sgcollectinfo-old.zip", "sgcollectinfo-new.zip"],
        ]

        await sg.run_sgcollect(tmp_path)

        assert len(sg.downloaded) == 1
        assert sg.downloaded[0][0] == "sgcollectinfo-new.zip"

    @pytest.mark.asyncio
    async def test_raises_when_no_new_zip_appears(self, tmp_path: Path):
        sg = FakeSyncGateway()
        sg.caddy_snapshots = [[], []]

        with pytest.raises(CblTestError, match="No new sgcollect zip found"):
            await sg.run_sgcollect(tmp_path)

        assert sg.downloaded == []

    @pytest.mark.asyncio
    async def test_raises_when_more_than_one_new_zip_appears(self, tmp_path: Path):
        sg = FakeSyncGateway()
        sg.caddy_snapshots = [[], ["sgcollectinfo-a.zip", "sgcollectinfo-b.zip"]]

        with pytest.raises(
            CblTestError, match="Expected exactly one new sgcollect zip"
        ):
            await sg.run_sgcollect(tmp_path)

        assert sg.downloaded == []


class TestRunSgcollects:
    @pytest.mark.asyncio
    async def test_collects_from_every_node(self, tmp_path: Path):
        sg1 = FakeSyncGateway("sg1.example.com")
        sg1.caddy_snapshots = [[], ["sgcollectinfo-a.zip"]]
        sg2 = FakeSyncGateway("sg2.example.com")
        sg2.caddy_snapshots = [[], ["sgcollectinfo-b.zip"]]

        output_dir = tmp_path / "logs"
        collected = await run_sgcollects([sg1, sg2], output_dir)

        assert collected == [
            output_dir / f"{sg1.hostname.replace('.', '_')}-sgcollectinfo-a.zip",
            output_dir / f"{sg2.hostname.replace('.', '_')}-sgcollectinfo-b.zip",
        ]
        assert output_dir.is_dir()

    @pytest.mark.asyncio
    async def test_one_node_failing_does_not_stop_the_others(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        sg1 = FakeSyncGateway("sg1.example.com")
        sg1.caddy_snapshots = [[], []]  # no new zip ever appears -> run_sgcollect fails
        sg2 = FakeSyncGateway("sg2.example.com")
        sg2.caddy_snapshots = [[], ["sgcollectinfo-b.zip"]]

        with caplog.at_level(logging.ERROR, logger="CBL"):
            collected = await run_sgcollects([sg1, sg2], tmp_path)

        expected = tmp_path / f"{sg2.hostname.replace('.', '_')}-sgcollectinfo-b.zip"
        assert collected == [expected]
        assert sg1.downloaded == []

        error_messages = [
            r.getMessage() for r in caplog.records if r.levelname == "ERROR"
        ]
        assert any("sg1.example.com" in m for m in error_messages)
        assert any("1/2 node(s) failed" in m for m in error_messages)

    @pytest.mark.asyncio
    async def test_empty_sync_gateway_list_collects_nothing(self, tmp_path: Path):
        collected = await run_sgcollects([], tmp_path)
        assert collected == []
        assert tmp_path.is_dir()
