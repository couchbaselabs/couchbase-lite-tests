"""Helpers so JS (browser) CBL can talk to Edge Server over ws://, not HTTPS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyjson5
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.syncgateway import SyncGateway


def prepare_es_replication_for_sgw(config: dict[str, Any], sync_gateway: SyncGateway, db_name: str) -> dict[str, Any]:
    """Point ES at SG using the live URL and drop pinned_cert when SG is HTTP."""
    replications = config.setdefault("replications", [{}])
    if not replications:
        replications.append({})
    replications[0]["source"] = sync_gateway.replication_url(db_name)
    if not sync_gateway.secure:
        replications[0].pop("pinned_cert", None)
    for db in config.get("databases", {}).values():
        if isinstance(db, dict):
            db.setdefault("create", True)
    # Local Docker has no travel.cblite2 zip. create:true alone yields
    # _default._default only — declare replication collections so ES creates them.
    _ensure_db_collections_for_replications(config)
    return config


def _ensure_db_collections_for_replications(config: dict[str, Any]) -> None:
    databases = config.get("databases")
    if not isinstance(databases, dict):
        return
    for repl in config.get("replications", []):
        if not isinstance(repl, dict):
            continue
        target = repl.get("target")
        collections = repl.get("collections")
        if not isinstance(target, str) or not isinstance(collections, list):
            continue
        db = databases.get(target)
        if not isinstance(db, dict):
            continue
        existing = db.get("collections")
        if existing is None:
            db["collections"] = list(collections)
        elif isinstance(existing, list):
            for name in collections:
                if name not in existing:
                    existing.append(name)
        elif isinstance(existing, dict):
            for name in collections:
                existing.setdefault(name, {})


def assert_http_only_es_config(config_path: str | Path) -> None:
    """Fail fast if the ES config enables TLS — browser CBL-JS cannot use HTTPS."""
    path = Path(config_path)
    with path.open(encoding="utf-8") as handle:
        config = pyjson5.loads(handle.read())
    if config.get("https"):
        raise AssertionError(
            f"{path} has an 'https' block. JavaScript/browser CBL cannot "
            "replicate to Edge Server over HTTPS/WSS; use HTTP + ws://."
        )


def js_edge_replicator_url(edge_server: EdgeServer, db_name: str) -> str:
    """Replication URL for JS CBL. Must be ws://, never wss://."""
    url = edge_server.replication_url(db_name)
    if not url.startswith("ws://"):
        raise AssertionError(
            f"JS CBL requires ws:// Edge Server URL, got {url}. Remove the https block from the local ES config."
        )
    return url
