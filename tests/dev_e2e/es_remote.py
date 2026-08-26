"""Run existing SG-targeted e2e tests against Edge Server as the remote.

`--cbl-remote=es` replaces `cblpytest.sync_gateways[0]` with this adapter and
points `CouchbaseCloud.configure_dataset` at an HTTP Edge Server database
loaded from the same `{name}-sg.json` files used for Sync Gateway.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import aiofiles
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.edgeserver import BulkDocOperation, EdgeServer
from cbltest.api.jsonserializable import JSONDictionary
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.asyncfile import write_json_file
from es_ws import js_edge_replicator_url

# Tests that need SG sync functions, users/roles, or CBS N1QL.
ES_SKIP_FILES = frozenset(
    {
        "test_fest.py",
        "test_replication_auto_purge.py",
        "test_replication_upgrade.py",
        "test_replication_xdcr.py",
        "test_multipeer.py",
        "test_encrypted_properties.py",
        "test_edge_server_cbl.py",
        "test_custom_conflict.py",
    }
)
ES_SKIP_TEST_NAMES = frozenset(
    {
        "test_pull_channels_filter",
        "test_replicate_public_channel",
        "test_reset_checkpoint_push",
        "test_reset_checkpoint_pull",
        "test_blob_replication",
        "test_push_document_ids_filter",
        "test_pull_document_ids_filter",
        "test_custom_pull_filter",
    }
)


def collections_from_sg_config(dataset_config: dict[str, Any]) -> list[str]:
    """Return `scope.collection` names from an *-sg-config.json payload."""
    nested = dataset_config.get("config", {})
    scopes = nested.get("scopes", {})
    names: list[str] = []
    if not isinstance(scopes, dict):
        return names
    for scope, scope_body in scopes.items():
        if not isinstance(scope_body, dict):
            continue
        collections = scope_body.get("collections", {})
        if not isinstance(collections, dict):
            continue
        for collection in collections:
            names.append(f"{scope}.{collection}")
    return names


class EsRemote:
    """Duck-types the Sync Gateway methods the SG e2e tests call."""

    using_rosmar = False
    secure = False
    port = 59840

    def __init__(self, edge: EdgeServer, dataset_path: Path):
        self._edge = edge
        self._dataset_path = dataset_path
        self._original_sync_gateways: list[Any] = []
        self.hostname = edge.hostname
        self.scheme = edge.scheme

    async def close(self) -> None:
        for sg in self._original_sync_gateways:
            await sg.close()

    def tls_cert(self) -> str | None:
        return None

    def replication_url(self, db_name: str, load_balancer: str | None = None) -> str:
        return js_edge_replicator_url(self._edge, db_name)

    async def get_all_documents(
        self,
        db_name: str,
        scope: str = "_default",
        collection: str = "_default",
        include_docs: bool = False,
    ):
        return await self._edge.get_all_documents(
            db_name,
            scope=scope,
            collection=collection,
            include_docs=include_docs,
        )

    async def get_document(
        self,
        db_name: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ):
        return await self._edge.get_document(
            db_name, doc_id, scope=scope, collection=collection
        )

    async def update_documents(
        self,
        db_name: str,
        updates: list[DocumentUpdateEntry],
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        ops = [
            BulkDocOperation(
                u.to_json(),
                _id=u.id,
                rev=u.rev,
                optype="update" if u.rev else "create",
            )
            for u in updates
        ]
        await self._edge.bulk_doc_op(ops, db_name, scope=scope, collection=collection)

    async def delete_document(
        self,
        doc_id: str,
        revid: str,
        db_name: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        await self._edge.delete_document(doc_id, revid, db_name, scope, collection)

    async def purge_document(
        self,
        doc_id: str,
        db_name: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        keyspace = self._edge.keyspace_builder(db_name, scope, collection)
        await self._edge._send_request(
            "post",
            f"/{keyspace}/_purge",
            JSONDictionary({doc_id: ["*"]}),
        )

    async def add_user(self, *args: Any, **kwargs: Any) -> None:
        """ES has no SG channel ACL; user1 is a static admin."""

    async def add_role(self, *args: Any, **kwargs: Any) -> None:
        """ES has no SG roles."""

    def create_collection_access_dict(self, input_data: dict[str, list[str]]) -> dict:
        return input_data

    async def configure_dataset(
        self,
        dataset_path: Path,
        dataset_name: str,
        sg_config_options: list[str] | None = None,
    ) -> None:
        del sg_config_options
        config_filepath = dataset_path / f"{dataset_name}-sg-config.json"
        data_filepath = dataset_path / f"{dataset_name}-sg.json"
        if not config_filepath.exists():
            raise FileNotFoundError(config_filepath)

        async with aiofiles.open(config_filepath, encoding="utf-8") as handle:
            dataset_config = json.loads(await handle.read())

        collections = collections_from_sg_config(dataset_config)
        es_config = {
            "$schema": "https://packages.couchbase.com/couchbase-edge-server/config_schema.json",
            "interface": "0.0.0.0:59840",
            "enable_anonymous_users": True,
            "cors": {
                "origin": ["http://localhost:5173"],
                "headers": ["Authorization", "Content-Type"],
            },
            "databases": {
                dataset_name: {
                    "path": f"/home/ec2-user/database/{dataset_name}.cblite2",
                    "create": True,
                    "enable_adhoc_queries": True,
                    "enable_client_writes": True,
                    "enable_client_sync": True,
                    "collections": collections,
                }
            },
            "users": "/home/ec2-user/user/users.json",
            "logging": {
                "console": True,
                "file": {"dir": "/home/ec2-user/log", "format": "text"},
            },
        }
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False
        ) as handle:
            runtime_config = Path(handle.name)
        await write_json_file(str(runtime_config), es_config)

        await self._edge.configure_dataset(
            db_name=dataset_name, config_file=str(runtime_config)
        )
        await _wait_for_es(self._edge)

        if data_filepath.exists() and data_filepath.stat().st_size > 0:
            await self._load_sg_json(dataset_name, data_filepath)

    async def _load_sg_json(self, db_name: str, path: Path) -> None:
        last_scope = ""
        last_coll = ""
        collected: list[BulkDocOperation] = []

        async def flush() -> None:
            if not collected:
                return
            await self._edge.bulk_doc_op(
                collected, db_name, scope=last_scope, collection=last_coll
            )
            collected.clear()

        async with aiofiles.open(path, encoding="utf-8") as handle:
            async for line in handle:
                line = line.strip()
                if not line:
                    continue
                doc = json.loads(line)
                scope = str(doc.pop("scope", "_default"))
                collection = str(doc.pop("collection", "_default"))
                if (
                    scope != last_scope
                    or collection != last_coll
                    or len(collected) >= 200
                ) and collected:
                    await flush()
                last_scope = scope
                last_coll = collection
                collected.append(BulkDocOperation(doc, _id=doc.get("_id")))
        await flush()


async def _wait_for_es(edge: EdgeServer, timeout: float = 30) -> None:
    elapsed = 0.0
    while elapsed < timeout:
        try:
            await edge.get_version()
            return
        except Exception:
            await asyncio.sleep(0.5)
            elapsed += 0.5
    raise TimeoutError("Edge Server did not become ready after configure_dataset")


def install_es_remote(cblpytest: Any, dataset_path: Path) -> EsRemote:
    if not cblpytest.edge_servers:
        raise RuntimeError(
            "--cbl-remote=es requires an edge-servers entry in the test config"
        )
    remote = EsRemote(cblpytest.edge_servers[0], dataset_path)
    remote._original_sync_gateways = list(cblpytest.sync_gateways)
    cblpytest.sync_gateways[:] = [remote]

    async def _configure(
        self: CouchbaseCloud,
        path: Path,
        dataset_name: str,
        sg_config_options: list[str] | None = None,
    ) -> None:
        del self
        await remote.configure_dataset(path, dataset_name, sg_config_options)

    CouchbaseCloud.configure_dataset = _configure  # type: ignore[method-assign]
    return remote
