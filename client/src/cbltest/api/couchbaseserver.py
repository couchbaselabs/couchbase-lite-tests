import os
import platform
import subprocess
import tempfile
import time
import zipfile
from collections import OrderedDict
from collections.abc import Callable, Sequence
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar, cast

import aiohttp

T = TypeVar("T")
import json
from urllib.parse import quote_plus, urlparse

import requests
import tenacity
from couchbase import subdocument
from couchbase.auth import PasswordAuthenticator
from couchbase.bucket import Bucket
from couchbase.cluster import Cluster
from couchbase.exceptions import (
    BucketAlreadyExistsException,
    BucketDoesNotExistException,
    CollectionAlreadyExistsException,
    CouchbaseException,
    DocumentNotFoundException,
    QueryIndexAlreadyExistsException,
    ScopeAlreadyExistsException,
)
from couchbase.management.buckets import CreateBucketSettings
from couchbase.management.options import CreatePrimaryQueryIndexOptions
from couchbase.options import ClusterOptions, ClusterTimeoutOptions, MutateInOptions, ReplaceOptions
from opentelemetry.trace import get_tracer

from cbltest import bucketpool
from cbltest.api.error import CblTestError
from cbltest.logging import cbl_info, cbl_warning
from cbltest.utils import async_retry_assert, retry_assert
from cbltest.version import VERSION


class BucketCleanupMode(StrEnum):
    """How the harness returns a Couchbase Server bucket to an empty state between tests."""

    #: Drop the bucket and create a new one for the next test.
    DELETE = "delete"

    #: Empty the bucket in place and keep its scopes, collections and indexes.
    PURGE = "purge"


#: How many buckets may exist on the cluster at once when buckets are reused.
MAX_BUCKETS = 5


class BucketPool:
    """
    Tracks the buckets on one Couchbase Server cluster and caps how many exist at once.

    Only :attr:`BucketCleanupMode.PURGE` needs a pool.  Purging keeps a bucket alive after
    every test, so without a cap the cluster collects one bucket per distinct name a run
    asks for.  The pool adopts buckets it did not create, so a run that was interrupted
    before its buckets were cleaned up does not push the cluster over the cap.
    """

    def __init__(self, server: "CouchbaseServer", max_buckets: int = MAX_BUCKETS) -> None:
        """
        :param server: The Couchbase Server node the pool creates and deletes buckets through
        :param max_buckets: The most buckets that may exist at once (default 10)
        """
        if max_buckets < 1:
            raise ValueError(f"max_buckets must be at least 1, got {max_buckets}")

        self.__server = server
        self.__max_buckets = max_buckets
        # Least recently used first, so the head is what gets evicted.
        self.__buckets: OrderedDict[str, None] = OrderedDict()

    @property
    def max_buckets(self) -> int:
        """The most buckets that may exist on the cluster at once."""
        return self.__max_buckets

    @property
    def bucket_names(self) -> list[str]:
        """The buckets the pool knows about, least recently used first."""
        return list(self.__buckets)

    def create_bucket(
        self,
        name: str,
        num_replicas: int = 0,
        retries: int = 60,
        interval: float = 2.0,
    ) -> bool:
        """
        Returns a ready bucket with the given name, creating it if the cluster does not have
        one already.  If the cluster is at its bucket cap, the least recently used bucket is
        deleted first to make room.

        :param name: The name of the bucket
        :param num_replicas: The number of replicas for the bucket (default 0)
        :param retries: Number of readiness checks to perform (default 60)
        :param interval: Seconds to wait between checks (default 2.0)
        :return: True if the bucket was created, False if it already existed
        """
        self.__adopt_existing()
        if name not in self.__buckets:
            self.__make_room()

        created = self.__server._create_bucket(name, num_replicas, retries, interval)
        self.__buckets[name] = None
        self.__buckets.move_to_end(name)
        return created

    def __adopt_existing(self) -> None:
        """
        Lines the pool up with the cluster: buckets that are gone are forgotten, and buckets
        the pool never created are adopted as the oldest, so they are evicted first.
        """
        existing = set(self.__server.get_bucket_names())

        for name in [name for name in self.__buckets if name not in existing]:
            del self.__buckets[name]

        for name in existing:
            if name not in self.__buckets:
                self.__buckets[name] = None
                self.__buckets.move_to_end(name, last=False)

    def __make_room(self) -> None:
        """Deletes least recently used buckets until one more bucket fits under the cap."""
        while len(self.__buckets) >= self.__max_buckets:
            oldest, _ = self.__buckets.popitem(last=False)
            cbl_info(f"Bucket pool is full ({self.__max_buckets}), deleting '{oldest}' to make room")
            self.__server.delete_bucket(oldest)
            self.__server._block_until_bucket_deleted(oldest)


class CouchbaseServer:
    """
    A class that interacts with a Couchbase Server cluster
    """

    def ensure_cluster_healthy(self, cbs_servers: Sequence["CouchbaseServer"]) -> None:
        """
        Ensures all CBS nodes are in the cluster and healthy.
        Uses credentials from this instance to manage the cluster.

        :param cbs_servers: List of CouchbaseServer instances to check (including self)
        """
        if len(cbs_servers) < 2:
            return

        try:
            resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default")
            resp.raise_for_status()
            cluster_data = resp.json()
        except Exception as e:
            raise CblTestError("Cannot connect to CBS cluster") from e

        nodes_in_cluster = cluster_data.get("nodes", [])

        for cbs_node in cbs_servers:
            # Skip self - can't add the primary node to its own cluster
            if cbs_node.hostname == self.__hostname:
                continue

            node_in_cluster = False
            node_needs_recovery = False

            for cluster_node in nodes_in_cluster:
                hostname = cluster_node.get("hostname", "").split(":")[0]
                alt_hostname = cluster_node.get("alternateAddresses", {}).get("external", {}).get("hostname", "")

                if cbs_node.hostname in [hostname, alt_hostname]:
                    node_in_cluster = True
                    cluster_membership = cluster_node.get("clusterMembership")

                    if cluster_membership == "inactiveFailed":
                        node_needs_recovery = True
                    break

            # Only act if node needs recovery or is missing
            if node_needs_recovery:
                self.recover(cbs_node)
                self.rebalance()
                time.sleep(5)
            elif not node_in_cluster:
                self.add_node(cbs_node)
                self.rebalance()
                time.sleep(5)
            # If node is in cluster and active, do nothing

        if not self.wait_for_cluster_healthy(timeout=120):
            raise CblTestError("CBS cluster did not become healthy")

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        cleanup_mode: BucketCleanupMode = BucketCleanupMode.PURGE,
    ) -> None:
        """
        :param url: The URL of any node in the cluster
        :param username: The administrator username to connect with
        :param password: The administrator password to connect with
        :param cleanup_mode: How buckets are emptied between tests (default purge)
        """
        self.__tracer = get_tracer(__name__, VERSION)
        with self.__tracer.start_as_current_span("connect_to_couchbase_server"):
            if "://" not in url:
                url = f"couchbase://{url}"

            # Parse URL to extract hostname and REST port
            self._parse_connection_url(url)
            self.__url = url

            auth = PasswordAuthenticator(username, password)
            opts = ClusterOptions(
                auth,
                timeout_options=ClusterTimeoutOptions(
                    # mac dns resolution can be very slow, default timeout is 250ms
                    dns_srv_timeout=timedelta(seconds=10)
                ),
            )
            self.__username = username
            self.__password = password
            try:
                self.__cluster = Cluster(url, opts)
            except CouchbaseException as e:
                cbl_warning(
                    f"Initial connection to Couchbase Server {url} with {username=} password=<redacted> failed with: {e}"
                )
                raise
            self.__cluster.wait_until_ready(timedelta(seconds=10))

            # Create a reusable HTTP session for REST API calls
            self.__http_session = requests.Session()
            self.__http_session.auth = (username, password)

            self.__cleanup_mode = cleanup_mode
            # Deleting a bucket between tests leaves nothing to reuse, so nothing needs capping.
            self.__bucket_pool = BucketPool(self) if cleanup_mode is BucketCleanupMode.PURGE else None

    def _parse_connection_url(self, url: str) -> None:
        """
        Parse connection URL to extract hostname and REST port.

        :param url: Connection URL (e.g., "couchbase://hostname:port")
        """
        parsed = urlparse(url)
        self.__hostname = parsed.hostname or parsed.netloc.split(":")[0]
        self.__rest_port = parsed.port or 8091

    def __str__(self) -> str:
        return f"{type(self).__name__} {self.__hostname}:{self.__rest_port}"

    @property
    def hostname(self) -> str:
        """
        Gets the hostname of this Couchbase Server instance.

        :return: The hostname
        """
        return self.__hostname

    @property
    def cleanup_mode(self) -> BucketCleanupMode:
        """How :func:`clean_bucket` empties a bucket between tests."""
        return self.__cleanup_mode

    @property
    def bucket_pool(self) -> BucketPool | None:
        """
        The pool that caps how many buckets exist on this cluster at once, or None when
        buckets are deleted between tests and there is nothing to reuse.
        """
        return self.__bucket_pool

    @tenacity.retry(
        wait=tenacity.wait_fixed(1),
        stop=tenacity.stop_after_attempt(10),
        reraise=True,
        retry=tenacity.retry_if_exception_type(CouchbaseException),
    )
    def get_bucket(self, name: str) -> Bucket:
        """
        Opens a bucket on the cluster, retrying while it is not yet available
        (e.g. shortly after creation).

        :param name: The name of the bucket to open
        """
        return self.__cluster.bucket(name)

    def create_collections(self, bucket: str, scope: str, names: list[str]) -> None:
        """
        A function that will create a specified set of collections in the specified scope
        which resides in the specified bucket

        :param bucket: The bucket name in which the scope resides
        :param scope: The scope in which to create the collections.  It will be created
                      if it doesn't already exist, unless it is the default scope
        :param names: The names of the collections to create
        """
        with self.__tracer.start_as_current_span(
            "Create Scope",
            attributes={"cbl.scope.name": scope, "cbl.bucket.name": bucket},
        ):
            bucket_obj = self.get_bucket(bucket)
            c = bucket_obj.collections()
            try:
                if scope != "_default":
                    c.create_scope(scope)
            except ScopeAlreadyExistsException:
                pass

            for name in names:
                with self.__tracer.start_as_current_span(
                    "Create Collection",
                    attributes={
                        "cbl.scope.name": scope,
                        "cbl.bucket.name": bucket,
                        "cbl.collection.name": name,
                    },
                ):
                    try:
                        if name != "_default":
                            c.create_collection(scope_name=scope, collection_name=name)
                    except CollectionAlreadyExistsException:
                        pass

                self._wait_for_collection_ready(bucket_obj, scope, name)

    @tenacity.retry(
        wait=tenacity.wait_fixed(1),
        stop=tenacity.stop_after_attempt(10),
        reraise=True,
        retry=tenacity.retry_if_exception_type(CblTestError),
    )
    def _wait_for_collection_ready(self, bucket: Bucket, scope: str, name: str) -> None:
        """
        Probes a freshly created collection by reading a nonexistent document from it,
        retrying until the collection responds.

        :param bucket: The bucket the collection resides in
        :param scope: The scope the collection resides in
        :param name: The name of the collection to probe
        """
        try:
            bucket.scope(scope).collection(name).get("_nonexistent")
        except DocumentNotFoundException:
            pass
        except Exception as e:
            raise CblTestError(f"Unable to properly create {bucket.name}.{scope}.{name} in Couchbase Server") from e

    def create_bucket(
        self,
        name: str,
        num_replicas: int = 0,
        retries: int = 60,
        interval: float = 2.0,
    ) -> bool:
        """
        Creates a bucket with a given name that Sync Gateway can use, reusing an existing
        bucket of that name if the cluster still has one.

        In :attr:`BucketCleanupMode.PURGE` this goes through :attr:`bucket_pool`, so asking
        for a bucket when the cluster is already at its cap deletes the least recently used
        one to make room.

        :param name: The name of the bucket to create
        :param num_replicas: The number of replicas for the bucket (default 0)
        :param retries: Number of readiness checks to perform (default 60)
        :param interval: Seconds to wait between checks (default 2.0)
        :return: True if the bucket was created, False if it already existed
        """
        if self.__bucket_pool is not None:
            return self.__bucket_pool.create_bucket(name, num_replicas, retries, interval)

        return self._create_bucket(name, num_replicas, retries, interval)

    def _create_bucket(
        self,
        name: str,
        num_replicas: int = 0,
        retries: int = 60,
        interval: float = 2.0,
    ) -> bool:
        """
        Creates a bucket without consulting the pool.

        Not public: callers want :func:`create_bucket`, which keeps the cluster under its
        bucket cap.  This exists for :class:`BucketPool` to call once it has made room.
        """
        with self.__tracer.start_as_current_span("create_bucket", attributes={"cbl.bucket.name": name}):
            mgr = self.__cluster.buckets()
            settings = CreateBucketSettings(
                name=name,
                flush_enabled=True,
                ram_quota_mb=512,
                num_replicas=num_replicas,
            )
            newly_created = True
            try:
                mgr.create_bucket(settings)
            except BucketAlreadyExistsException:
                newly_created = False

            # Bucket creation is asynchronous in the cluster. Wait until it is healthy
            # and responding before returning so callers can safely proceed.
            retry_assert(
                lambda: self._check_bucket_ready(name),
                tenacity.wait_fixed(interval),
                tenacity.stop_after_attempt(retries),
            )
            return newly_created

    def _check_bucket_ready(self, name: str) -> None:
        """
        Asserts that a bucket is ready to use, naming the first condition it fails.

        :param name: The bucket to check
        """
        assert self.bucket_healthy(name), f"bucket '{name}' is not healthy on all nodes"
        assert self.bucket_kv_responding(name), f"bucket '{name}' is not responding to KV stats requests"
        assert self.collections_ready(name), f"bucket '{name}' collection manifest is not available"

    def wait_for_indexes_removed(self, bucket: str) -> None:
        """
        CBL-4977: A bucket recreated with the same name can have stale indexes that are
        still being deleted asynchronously.  Sync Gateway will then wrongly detect that
        the indexes already exist, and querying later fails with index-not-available
        once the deletion catches up.  Wait for them to be gone before Sync Gateway
        gets a chance to look.

        .. note:: Call this after the bucket's collections have been created, otherwise
            QueryIndexManager will not return the pending-to-removed indexes that were
            created for those collections.

        :param bucket: The bucket to wait on
        """
        retry_assert(
            lambda: self._check_all_indexes_removed(bucket),
            tenacity.wait_fixed(2),
            tenacity.stop_after_attempt(10),
        )

    def _check_all_indexes_removed(self, bucket: str) -> None:
        count = self.indexes_count(bucket)
        assert count == 0, f"{count} indexes remain in '{bucket}' bucket"

    def delete_bucket(self, name: str) -> None:
        """
        Removes a bucket, and everything in it, from the Couchbase cluster.

        Between tests call :func:`clean_bucket` instead, which follows :attr:`cleanup_mode`.
        Delete a bucket when a test needs it to be gone, or when the bucket pool needs room.

        :param name: The name of the bucket to delete
        """
        with self.__tracer.start_as_current_span("delete_bucket", attributes={"cbl.bucket.name": name}):
            try:
                mgr = self.__cluster.buckets()
                mgr.drop_bucket(name)
            except BucketDoesNotExistException:
                pass

    async def clean_bucket(self, name: str) -> None:
        """
        Returns a bucket to an empty state, the way :attr:`cleanup_mode` asks for.

        In delete mode the bucket is dropped and this waits until the cluster reports it
        gone.  In purge mode the documents go but the bucket, its scopes, its collections
        and its indexes stay, so the next test does not pay to rebuild them.

        :param name: The name of the bucket to empty
        """
        if self.__cleanup_mode is BucketCleanupMode.PURGE:
            await self.purge_bucket(name)
            return

        self.delete_bucket(name)
        await self.wait_for_bucket_deleted(name)

    async def purge_bucket(self, name: str, timeout: float = bucketpool.DEFAULT_TIMEOUT) -> str:
        """
        Removes every document, and every xattr, from all collections of a bucket.  The
        bucket, its scopes, its collections and its indexes stay as they are.

        A Sync Gateway tombstone is a deleted document that still carries a ``_sync`` xattr.
        Neither a query nor a key/value read can see one, so the work is done over a DCP feed
        by the ``bucketpool`` helper, downloaded into ``tests/.tools``.

        :param name: The name of the bucket to empty
        :param timeout: Seconds the feed and the purge together are allowed to take
        :return: A one line summary of how many documents were seen and purged
        """
        with self.__tracer.start_as_current_span("purge_bucket", attributes={"cbl.bucket.name": name}):
            return await bucketpool.purge_bucket(
                connection_string=self.__url,
                management_url=f"http://{self.__hostname}:8091",
                username=self.__username,
                password=self.__password,
                bucket=name,
                timeout=timeout,
            )

    def bucket_healthy(self, bucket_name: str) -> bool:
        """
        Returns True only if the bucket is healthy on all nodes.
        """
        resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default/buckets/{bucket_name}")
        if resp.status_code != 200:
            return False

        bucket = resp.json()
        nodes = bucket.get("nodes", [])
        if not nodes:
            return False

        for node in nodes:
            if node.get("status") != "healthy":
                return False
        return True

    def bucket_kv_responding(self, bucket_name: str) -> bool:
        """
        Returns True if KV stats endpoint responds successfully.
        This is a practical readiness signal for DCP / SDK / SG.
        """
        resp = self.__http_session.get(
            f"http://{self.__hostname}:8091/pools/default/buckets/{bucket_name}/stats",
            timeout=5,
        )
        return resp.status_code == 200

    def collections_ready(self, bucket_name: str) -> bool:
        """
        Checks if the collections manifest is available.
        """
        resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default/buckets/{bucket_name}/scopes")
        return resp.status_code == 200

    def get_bucket_names(self) -> list[str]:
        """
        Gets the names of all buckets in the Couchbase cluster

        :return: A list of bucket names
        """
        with self.__tracer.start_as_current_span("get_bucket_names"):
            buckets_resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default/buckets")
            buckets_resp.raise_for_status()
            buckets_data = buckets_resp.json()
            return [bucket["name"] for bucket in buckets_data]

    def _check_bucket_deleted(self, bucket_name: str) -> None:
        """Asserts that the cluster no longer reports the bucket."""
        try:
            # If bucket no longer exists, deletion is complete
            still_present = self.bucket_healthy(bucket_name)
        except Exception:
            # Treat errors as "bucket gone"
            return
        assert not still_present, f"bucket '{bucket_name}' is still present"

    async def wait_for_bucket_deleted(
        self,
        bucket_name: str,
        max_retries: int = 30,
        retry_delay: float = 2.0,
    ) -> None:
        """
        Waits for a bucket to be fully deleted from the Couchbase cluster.
        Async because deletion is eventual and requires polling remote state.
        """

        async def _wait_for_bucket_deleted_poll() -> None:
            self._check_bucket_deleted(bucket_name)

        with self.__tracer.start_as_current_span(
            "wait_for_bucket_deleted", attributes={"cbl.bucket.name": bucket_name}
        ):
            await async_retry_assert(
                _wait_for_bucket_deleted_poll,
                tenacity.wait_fixed(retry_delay),
                tenacity.stop_after_attempt(max_retries),
            )

    def _block_until_bucket_deleted(
        self,
        bucket_name: str,
        max_retries: int = 30,
        retry_delay: float = 2.0,
    ) -> None:
        """
        Blocks until the cluster stops reporting the bucket.

        Not public: callers running in an event loop want :func:`wait_for_bucket_deleted`.
        This exists for :class:`BucketPool`, which evicts buckets from synchronous code.
        """
        with self.__tracer.start_as_current_span(
            "wait_for_bucket_deleted", attributes={"cbl.bucket.name": bucket_name}
        ):
            retry_assert(
                lambda: self._check_bucket_deleted(bucket_name),
                tenacity.wait_fixed(retry_delay),
                tenacity.stop_after_attempt(max_retries),
            )

    def restore_bucket(
        self,
        name: str,
        tools_path: Path,
        dataset_path: Path,
        dataset_name: str,
        *,
        repo_name: str | None = None,
        reset_expired_ttl: bool = False,
    ) -> None:
        """
        Restores a bucket from a backup source, replacing whatever the bucket held before.

        :param name: The name of the bucket to restore
        :param backup_source: The path to the backup source
        :param reset_expired_ttl: When True, restore already-expired documents
            with no expiry (``--replace-ttl expired --replace-ttl-with 0``) so
            they are not purged on access.
        """
        with self.__tracer.start_as_current_span(
            "restore_bucket",
            attributes={"cbl.bucket.name": name, "cbl.backup.source": dataset_name},
        ):
            bin_name = "cbbackupmgr.exe" if platform.system() == "Windows" else "cbbackupmgr"
            cbbackupmgr_path = tools_path / "cbbackupmgr" / bin_name
            if not cbbackupmgr_path.exists():
                raise FileNotFoundError(
                    "cbbackupmgr not found, please download it with the environment/aws/download_tool script"
                )

            # For historical reasons, dataset_path is pointing to the Sync Gateway dataset
            # directory.  This should be changed in the future, but for now to avoid breakage
            # just find the neighboring couchbase-server directory.
            data_filepath = dataset_path / ".." / "couchbase-server" / f"{dataset_name}.zip"
            if not data_filepath.exists():
                raise FileNotFoundError(f"Data file {dataset_name}.zip not found!")

            with tempfile.TemporaryDirectory(prefix="cbl_backup_") as tmpdir:
                extract_path = Path(tmpdir)
                try:
                    with zipfile.ZipFile(data_filepath, "r") as zf:
                        zf.extractall(extract_path)
                except zipfile.BadZipFile as e:
                    raise CblTestError(f"Backup zip '{data_filepath}' is invalid") from e

                restore_args = [
                    cbbackupmgr_path,
                    "restore",
                    "-a",
                    str(extract_path / dataset_name),
                    "-c",
                    self.__hostname,
                    "-r",
                    repo_name or dataset_name,
                    "-u",
                    self.__username,
                    "-p",
                    self.__password,
                    "--auto-create-buckets",
                    # Without this, cbbackupmgr skips every document the cluster holds a
                    # newer copy of, and the tombstones a purge leaves behind always are.
                    "--force-updates",
                    "--no-progress-bar",
                    "--disable-ft-indexes",  # requires access to private ports
                    "--disable-gsi-indexes",  # requires access to private ports
                    "--threads",
                    str(
                        os.cpu_count()
                    ),  # replace with os.process_cpu_count after CBL-8716, python upgrade to respect cgroups
                ]
                if reset_expired_ttl:
                    restore_args += [
                        "--replace-ttl",
                        "expired",
                        "--replace-ttl-with",
                        "0",
                    ]
                subprocess.run(restore_args, check=True)

    def indexes_count(self, bucket: str) -> int:
        """
        Returns the number of indexes that are in the specified bucket

        :param bucket: The bucket to check for indexes
        """
        with self.__tracer.start_as_current_span("indexes_count", attributes={"cbl.bucket.name": bucket}):
            index_mgr = self.__cluster.query_indexes()
            indexes = list(index_mgr.get_all_indexes(bucket))
            return len(indexes)

    def run_query(
        self,
        query: str,
        bucket: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> list[dict]:
        """
        Runs the specified query on the server.  The query may be formatted in a special way.

        :param query: The SQL++ query to run
        :param bucket: The bucket that the data to query is located in
        :param scope: The scope that the data to query is located in
        :param collection: The collection that the data to query is located in

        .. note::
            The FROM clause of this query can be a python substitution string ({}).  If
            it is, the FROM clause will be replaced with the proper bucket.scope.collection
            format at execution time.
        """
        actual_query = query.format(f"{bucket}.{scope}.{collection}")
        with self.__tracer.start_as_current_span("run_query", attributes={"cbl.query.name": actual_query}):
            query_obj = self.__cluster.query(actual_query)
            try:
                self.__cluster.query_indexes().create_primary_index(
                    bucket,
                    CreatePrimaryQueryIndexOptions(scope_name=scope, collection_name=collection),
                )
            except QueryIndexAlreadyExistsException:
                pass

            return [dict(result) for result in query_obj.execute()]

    def upsert_document(
        self,
        bucket: str,
        doc_id: str,
        document: dict,
        scope: str = "_default",
        collection: str = "_default",
        xattrs: dict[str, Any] | None = None,
    ) -> None:
        """
        Inserts a document into the specified bucket.scope.collection.

        :param bucket: The bucket name.
        :param scope: The scope name.
        :param collection: The collection name.
        :param doc_id: The document ID.
        :param document: The document content (a dictionary).
        :param xattrs: Xattrs to write in the same mutation as the body.
        """
        with self.__tracer.start_as_current_span(
            "insert_document",
            attributes={
                "cbl.bucket.name": bucket,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            coll = self.get_bucket(bucket).scope(scope).collection(collection)
            if not xattrs:
                coll.upsert(doc_id, document)
                return

            specs = [subdocument.upsert(key, value, xattr=True, create_parents=True) for key, value in xattrs.items()]
            specs.append(subdocument.replace("", document))
            coll.mutate_in(
                doc_id,
                specs,
                MutateInOptions(store_semantics=subdocument.StoreSemantics.UPSERT),
            )

    def get_document_with_cas(
        self,
        *,
        bucket: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> tuple[dict, int]:
        """
        Gets a document and the CAS it was read at, for a caller that means to write it back
        without clobbering whoever got in first.

        :param bucket: The bucket name.
        :param doc_id: The document ID.
        :param scope: The scope name.
        :param collection: The collection name.
        :return: The content and its CAS.
        :raises DocumentNotFoundException: if the document does not exist.
        """
        with self.__tracer.start_as_current_span(
            "get_document_with_cas",
            attributes={
                "cbl.bucket.name": bucket,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            coll = self.get_bucket(bucket).scope(scope).collection(collection)
            result = coll.get(doc_id)

            cas = result.cas
            assert cas is not None, f"Couchbase Server returned no CAS for document '{doc_id}'"
            return result.content_as[dict], cas

    def update_document(
        self,
        *,
        bucket: str,
        doc_id: str,
        document: dict,
        cas: int,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Writes a document, but only while it is still at the given CAS.

        :param bucket: The bucket name.
        :param doc_id: The document ID.
        :param document: The document content (a dictionary).
        :param cas: The CAS the content was read at, from get_document_with_cas.
        :param scope: The scope name.
        :param collection: The collection name.
        :raises CasMismatchException: if the document changed since it was read at cas.
            Whether to retry, and how often, is the caller's to decide.
        """
        with self.__tracer.start_as_current_span(
            "update_document",
            attributes={
                "cbl.bucket.name": bucket,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            coll = self.get_bucket(bucket).scope(scope).collection(collection)
            coll.replace(doc_id, document, ReplaceOptions(cas=cas))

    def delete_document(
        self,
        bucket: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Deletes a document from the specified bucket.scope.collection.

        :param bucket: The bucket name.
        :param doc_id: The document ID.
        :param scope: The scope name.
        :param collection: The collection name.
        :raises DocumentNotFoundException: if the document is already gone, so a caller racing
            another writer can tell its own delete from one it lost.
        """
        with self.__tracer.start_as_current_span(
            "delete_document",
            attributes={
                "cbl.bucket.name": bucket,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            coll = self.get_bucket(bucket).scope(scope).collection(collection)
            coll.remove(doc_id)

    def get_document(
        self,
        bucket: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> dict | None:
        """
        Gets a document from the specified bucket.scope.collection.

        :param bucket: The bucket name.
        :param doc_id: The document ID.
        :param scope: The scope name.
        :param collection: The collection name.
        :return: The document content as a dictionary, or None if not found.
        """
        with self.__tracer.start_as_current_span(
            "get_document",
            attributes={
                "cbl.bucket.name": bucket,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            try:
                body, _ = self.get_document_with_cas(
                    bucket=bucket,
                    doc_id=doc_id,
                    scope=scope,
                    collection=collection,
                )
                return body
            except DocumentNotFoundException:
                return None
            except Exception as e:
                raise CblTestError(f"Failed to get document '{doc_id}' from {bucket}.{scope}.{collection}") from e

    def upsert_document_xattr(
        self,
        bucket: str,
        doc_id: str,
        xattr_key: str,
        xattr_value: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Upserts an xattr on a document using subdocument operations

        :param bucket: The bucket containing the document
        :param doc_id: The ID of the document to update
        :param xattr_key: The xattr key to upsert
        :param xattr_value: The value to set for the xattr
        :param scope: The scope containing the document (default '_default')
        :param collection: The collection containing the document (default '_default')
        """
        with self.__tracer.start_as_current_span(
            "upsert_document_xattr",
            attributes={
                "cbl.bucket": bucket,
                "cbl.scope": scope,
                "cbl.collection": collection,
                "cbl.document.id": doc_id,
                "cbl.xattr.key": xattr_key,
            },
        ):
            col = self.get_bucket(bucket).scope(scope).collection(collection)
            col.mutate_in(
                doc_id,
                [subdocument.upsert(xattr_key, xattr_value, xattr=True, create_parents=True)],
            )

    def delete_document_xattr(
        self,
        bucket: str,
        doc_id: str,
        xattr_key: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Deletes an xattr from a document using subdocument operations

        :param bucket: The bucket containing the document
        :param doc_id: The ID of the document
        :param xattr_key: The xattr key to delete
        :param scope: The scope containing the document (default '_default')
        :param collection: The collection containing the document (default '_default')
        """
        with self.__tracer.start_as_current_span(
            "delete_document_xattr",
            attributes={
                "cbl.bucket": bucket,
                "cbl.scope": scope,
                "cbl.collection": collection,
                "cbl.document.id": doc_id,
                "cbl.xattr.key": xattr_key,
            },
        ):
            col = self.get_bucket(bucket).scope(scope).collection(collection)
            col.mutate_in(
                doc_id,
                [subdocument.remove(xattr_key, xattr=True)],
            )

    def start_xdcr(self, target: "CouchbaseServer", bucket_name: str) -> None:
        """
        Starts an XDCR replication from this cluster to the target cluster

        :param target: The target CouchbaseServer instance to replicate to
        :param source_bucket: The bucket on this cluster to replicate from
        :param target_bucket: The bucket on the target cluster to replicate to
        """
        with self.__tracer.start_as_current_span(
            "start_xdcr",
            attributes={
                "cbl.bucket": bucket_name,
                "cbl.target.hostname": target.__hostname,
            },
        ):
            # Get the existing remote cluster, if any...
            resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default/remoteClusters")
            resp.raise_for_status()
            resp_body = resp.json()
            remote_cluster_uuid: str | None = None
            for cluster in resp_body:
                if "name" in cluster and cast(str, cluster["name"]) == target.__hostname:
                    remote_cluster_uuid = cluster["uuid"]
                    break

            # https://docs.couchbase.com/server/current/learn/clusters-and-availability/xdcr-active-active-sgw.html#xdcr-active-active-sgw-prerequisites
            # Set the prerequisite properties.  These return 409 is they are already set.
            resp = self.__http_session.post(
                f"http://{self.__hostname}:8091/pools/default/buckets/{bucket_name}",
                data={"enableCrossClusterVersioning": "true"},
            )
            if resp.status_code != 409:
                resp.raise_for_status()

            resp = self.__http_session.post(
                f"http://{target.__hostname}:8091/pools/default/buckets/{bucket_name}",
                data={"enableCrossClusterVersioning": "true"},
            )
            if resp.status_code != 409:
                resp.raise_for_status()

            # https://docs.couchbase.com/server/current/manage/manage-xdcr/create-xdcr-replication.html#create-an-xdcr-replication-with-the-rest-api
            # Create the remote cluster, if necessary
            if remote_cluster_uuid is None:
                resp = self.__http_session.post(
                    f"http://{self.__hostname}:8091/pools/default/remoteClusters",
                    data={
                        "username": target.__username,
                        "password": target.__password,
                        "hostname": target.__hostname,
                        "name": target.__hostname,
                        "demandEncryption": 0,
                    },
                )
                resp.raise_for_status()

            needs_replication = True
            if remote_cluster_uuid is not None:
                # If the remote cluster didn't exist, the replication could not have existed
                # so skip the lookup.  Otherwise, check for a replication that is already
                # going out to the remote cluster in question.
                resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default/tasks")
                resp.raise_for_status()
                for task in resp.json():
                    if isinstance(task, dict) and task.get("type") == "xdcr":
                        task_id = task.get("id")
                        if task_id == f"{remote_cluster_uuid}/{bucket_name}/{bucket_name}":
                            needs_replication = False
                            break

            if needs_replication:
                resp = self.__http_session.post(
                    f"http://{self.__hostname}:8091/controller/createReplication",
                    data={
                        "fromBucket": bucket_name,
                        "toCluster": target.__hostname,
                        "toBucket": bucket_name,
                        "replicationType": "continuous",
                        "compressionLevel": "Auto",
                        "mobile": "active",
                    },
                )
                resp.raise_for_status()

    def stop_xcdr(self, target: "CouchbaseServer", bucket_name: str) -> None:
        """
        Stops an XDCR replication from this cluster to the target cluster.  Note
        that this does not remove the remote cluster.

        :param target: The target CouchbaseServer instance to replicate to
        :param source_bucket: The bucket on this cluster to replicate from
        :param target_bucket: The bucket on the target cluster to replicate to
        """
        with self.__tracer.start_as_current_span(
            "stop_xdcr",
            attributes={
                "cbl.bucket": bucket_name,
                "cbl.target.hostname": target.__hostname,
            },
        ):
            # See if the remote cluster already exists
            resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default/remoteClusters")
            resp.raise_for_status()
            resp_body = resp.json()
            remote_cluster_uuid: str | None = None
            for cluster in resp_body:
                if "name" in cluster and cast(str, cluster["name"]) == target.__hostname:
                    remote_cluster_uuid = cluster["uuid"]
                    break

            if remote_cluster_uuid is None:
                return

            # See if the XDCR already exists
            resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default/tasks")
            resp.raise_for_status()
            xdcr_id: str | None = None
            for task in resp.json():
                if isinstance(task, dict) and task.get("type") == "xdcr":
                    task_id = task.get("id")
                    if task_id == f"{remote_cluster_uuid}/{bucket_name}/{bucket_name}":
                        xdcr_id = task_id
                        break

            if xdcr_id is not None:
                encoded = quote_plus(xdcr_id)
                resp = self.__http_session.delete(
                    f"http://{self.__hostname}:8091/controller/cancelXDCR/{encoded}",
                )
                resp.raise_for_status()

    def add_node(
        self,
        node_to_add: "CouchbaseServer",
        services: list[str] | None = None,
    ) -> None:
        """
        Adds a node to the cluster.

        :param node_to_add: The CouchbaseServer instance representing the node to add
        :param services: List of services to enable on the node (e.g. ["kv", "index", "n1ql"])
                        Defaults to ["kv", "index", "n1ql"] (data, index, query)
        """
        if services is None:
            services = ["kv", "index", "n1ql"]

        with self.__tracer.start_as_current_span(
            "add_node",
            attributes={
                "cbl.node.hostname": node_to_add.__hostname,
                "cbl.node.services": ",".join(services),
            },
        ) as span:
            # Try to get internal hostname (best effort - falls back to original on failure)
            def get_internal_hostname() -> str:
                node_resp = node_to_add.__http_session.get(
                    f"http://{node_to_add.__hostname}:8091/nodes/self",
                    timeout=5,
                )
                if node_resp.status_code != 200:
                    raise CblTestError(f"Status {node_resp.status_code}")
                internal = node_resp.json().get("hostname", "").split(":")[0]
                if not internal or internal.startswith("127."):
                    raise CblTestError("Invalid internal hostname")
                return internal

            try:
                hostname_to_use = self._retry(
                    get_internal_hostname,
                    max_attempts=3,
                    wait_seconds=5,
                    operation_name=f"Query node {node_to_add.__hostname}",
                )
            except Exception:
                # Best effort - use original hostname if we can't get internal
                hostname_to_use = node_to_add.__hostname

            def do_add_node() -> None:
                resp = self.__http_session.post(
                    f"http://{self.__hostname}:8091/controller/addNode",
                    data={
                        "hostname": hostname_to_use,
                        "user": self.__username,
                        "password": self.__password,
                        "services": ",".join(services),
                    },
                )
                if resp.status_code != 200:
                    raise CblTestError(f"Status {resp.status_code}: {resp.text}")

            self._retry(
                do_add_node,
                max_attempts=5,
                wait_seconds=1,
                operation_name=f"Add node {node_to_add.__hostname}",
            )

            if hostname_to_use != node_to_add.__hostname:
                # Leaving the cluster discards a node's alternate address, so external clients
                # (the TDK) lose their route to it until it is republished.  Sending no ports
                # publishes every port the node runs, matching what provisioning sets up.
                def do_set_alternate_address() -> None:
                    self.__http_session.put(
                        f"http://{node_to_add.__hostname}:8091/node/controller/setupAlternateAddresses/external",
                        data={"hostname": node_to_add.__hostname},
                    ).raise_for_status()

                try:
                    self._retry(
                        do_set_alternate_address,
                        max_attempts=5,
                        wait_seconds=2,
                        operation_name=f"Set alternate address for {node_to_add.__hostname}",
                    )
                except Exception as e:
                    raise CblTestError(
                        f"Failed to set alternate address for {node_to_add.__hostname}, "
                        f"external SDK connections to it will time out"
                    ) from e

                span.add_event(
                    "alternate_address_set",
                    attributes={"hostname": node_to_add.__hostname},
                )

    def rebalance(
        self,
        eject_node: "CouchbaseServer | None" = None,
        eject_failed_nodes: bool = False,
    ) -> None:
        """
        Rebalances the cluster with optional node ejection.

        Can be used for three scenarios:
        1. Rebalance in (after add_node): rebalance()
        2. Rebalance out (remove node): rebalance(eject_node=node)
        3. Rebalance after failover: rebalance() or rebalance(eject_failed_nodes=True)

        :param eject_node: Optional node to eject during rebalance (rebalance out)
        :param eject_failed_nodes: If True, removes all inactiveFailed nodes from cluster
        """
        attributes: dict[str, str | int | float] = {}
        if eject_node:
            attributes["cbl.node.eject"] = eject_node.hostname
        if eject_failed_nodes:
            attributes["cbl.eject_failed"] = "true"

        with self.__tracer.start_as_current_span(
            "rebalance",
            attributes=attributes,
        ):
            # Get cluster information
            pool_data = self._get_cluster_info()

            known_nodes = []
            ejected_nodes_list = []

            for node in pool_data.get("nodes", []):
                otp_node = node.get("otpNode")
                cluster_membership = node.get("clusterMembership")

                known_nodes.append(otp_node)

                # If we need to eject a specific node, find its OTP ID
                if eject_node:
                    hostname = node.get("hostname", "").split(":")[0]
                    alt_hostname = node.get("alternateAddresses", {}).get("external", {}).get("hostname", "")

                    if eject_node.hostname in [hostname, alt_hostname]:
                        ejected_nodes_list.append(otp_node)

                # Or eject all failed nodes if requested
                elif eject_failed_nodes and cluster_membership == "inactiveFailed":
                    ejected_nodes_list.append(otp_node)

            # If ejecting a specific node, make sure we found it
            if eject_node and not ejected_nodes_list:
                raise CblTestError(
                    f"Node {eject_node.hostname} not found in cluster. "
                    f"Available nodes: {[n.get('hostname') for n in pool_data.get('nodes', [])]}"
                )

            # Start rebalance
            data = {"knownNodes": ",".join(known_nodes)}
            if ejected_nodes_list:
                data["ejectedNodes"] = ",".join(ejected_nodes_list)

            def do_rebalance() -> None:
                resp = self.__http_session.post(
                    f"http://{self.__hostname}:8091/controller/rebalance",
                    data=data,
                )
                resp.raise_for_status()

            self._retry(do_rebalance, max_attempts=5, wait_seconds=1, operation_name="Rebalance")

            # Wait for rebalance to complete
            self._wait_for_rebalance_completion()

    def _retry(
        self,
        func: Callable[[], T],
        max_attempts: int = 3,
        wait_seconds: float = 1,
        operation_name: str = "operation",
    ) -> T:
        """
        Retry a function with exponential backoff and logging.

        :param func: The function to call (should take no arguments, use lambda if needed)
        :param max_attempts: Maximum number of attempts (default: 3)
        :param wait_seconds: Seconds to wait between attempts (default: 1)
        :param operation_name: Name for logging purposes
        :return: The result of the function call
        :raises: The last exception if all attempts fail
        """
        last_exception: Exception | None = None

        for attempt in range(max_attempts):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    cbl_warning(f"{operation_name} failed (attempt {attempt + 1}/{max_attempts}): {e}")
                    time.sleep(wait_seconds)

        # All attempts failed - last_exception is guaranteed to be set
        assert last_exception is not None
        raise last_exception

    def _get_cluster_info(self) -> dict:
        """
        Internal method to get cluster information from /pools/default.

        :return: Cluster pool data containing node information
        """
        resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default")
        resp.raise_for_status()
        return resp.json()

    def _find_node_otp(self, pool_data: dict, target_node: "CouchbaseServer", operation: str) -> str:
        """
        Internal method to find the OTP node ID for a given CouchbaseServer instance.
        Checks both regular hostname and alternate address (for AWS VPC deployments).

        :param pool_data: Cluster pool data from /pools/default
        :param target_node: The CouchbaseServer instance to find
        :param operation: Operation name (for error message, e.g., "failover", "recovery")
        :return: OTP node ID string
        :raises CblTestError: If node is not found in cluster
        """
        for node in pool_data.get("nodes", []):
            hostname = node.get("hostname", "").split(":")[0]
            otp_node = node.get("otpNode")

            # Check both regular hostname and alternate address
            if hostname == target_node.hostname:
                return otp_node

            # Check alternate address (AWS VPC external hostname)
            alt_addrs = node.get("alternateAddresses", {}).get("external", {})
            alt_hostname = alt_addrs.get("hostname", "")
            if alt_hostname == target_node.hostname:
                return otp_node

        # Node not found
        raise CblTestError(f"Node {target_node.hostname} not found in cluster for {operation}")

    def failover(self, node_to_failover: "CouchbaseServer") -> None:
        """
        Performs a hard failover on a node in the cluster (simulates sudden node failure).

        :param node_to_failover: The node to failover
        """
        # Get cluster information and find the node to failover
        pool_data = self._get_cluster_info()
        failover_node = self._find_node_otp(pool_data, node_to_failover, "failover")

        # Perform hard failover
        resp = self.__http_session.post(
            f"http://{self.__hostname}:8091/controller/failOver",
            data={"otpNode": failover_node},
        )
        resp.raise_for_status()

    def recover(self, node_to_recover: "CouchbaseServer") -> None:
        """
        Recovers a failed node and sets it to delta recovery mode.

        :param node_to_recover: The node to recover
        """
        # Get cluster information and find the node to recover
        pool_data = self._get_cluster_info()
        recovery_node = self._find_node_otp(pool_data, node_to_recover, "recovery")

        # Set recovery type to delta (faster than full recovery)
        resp = self.__http_session.post(
            f"http://{self.__hostname}:8091/controller/setRecoveryType",
            data={"otpNode": recovery_node, "recoveryType": "delta"},
        )
        resp.raise_for_status()

    def wait_for_cluster_healthy(self, timeout: int = 60, check_interval: int = 2) -> bool:
        """
        Waits for the cluster to become healthy after a failover or rebalance operation.
        Checks that all active nodes are healthy and vBuckets are available.

        :param timeout: Maximum time to wait in seconds (default: 60)
        :param check_interval: Time between health checks in seconds (default: 2)
        :return: True if cluster is healthy, False if timeout reached
        """
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                # Check cluster status
                resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default")
                resp.raise_for_status()
                pool_data = resp.json()

                # Check rebalance status
                if pool_data.get("rebalanceStatus", "none") != "none":
                    time.sleep(check_interval)
                    continue

                # Check active nodes are healthy
                all_healthy = all(
                    node.get("status") == "healthy"
                    for node in pool_data.get("nodes", [])
                    if node.get("clusterMembership") == "active"
                )

                if not all_healthy:
                    time.sleep(check_interval)
                    continue

                # Check bucket vBuckets
                buckets_resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default/buckets")
                buckets_resp.raise_for_status()

                all_buckets_healthy = True
                for bucket in buckets_resp.json():
                    vbucket_map = bucket.get("vBucketServerMap", {})
                    if not vbucket_map.get("serverList") or not vbucket_map.get("vBucketMap"):
                        all_buckets_healthy = False
                        break

                    # Check all vBuckets have active nodes
                    if any(not vb or vb[0] == -1 for vb in vbucket_map.get("vBucketMap", [])):
                        all_buckets_healthy = False
                        break

                if not all_buckets_healthy:
                    time.sleep(check_interval)
                    continue

                return True

            except Exception:
                time.sleep(check_interval)

        return False

    def _wait_for_rebalance_completion(self, timeout_seconds: int = 300) -> None:
        """
        Waits for a rebalance operation to complete.

        :param timeout_seconds: Maximum time to wait (default 300 seconds / 5 minutes)
        """
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            resp = self.__http_session.get(f"http://{self.__hostname}:8091/pools/default/rebalanceProgress")
            resp.raise_for_status()
            status = resp.json()

            if status.get("status") == "none":
                return
            # wait for 5 seconds before calling the API again
            time.sleep(5)

        raise CblTestError(f"Rebalance did not complete within {timeout_seconds} seconds")

    async def stop_server(self) -> None:
        """
        Stop the Couchbase Server service via shell2http.
        """
        async with (
            aiohttp.ClientSession() as session,
            session.get(f"http://{self.hostname}:20001/stop-cbs") as resp,
        ):
            if resp.status != 200:
                body = await resp.text()
                raise CblTestError(f"Failed to stop CBS: {resp.status} - {body}")

    async def start_server(self, port: int = 8091) -> None:
        """
        Start the Couchbase Server service via shell2http.

        :param port: REST API port to wait for readiness (default 8091)
        """
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                f"http://{self.hostname}:20001/start-cbs",
                data=json.dumps({"port": port}),
                headers={"Content-Type": "application/json"},
            ) as resp,
        ):
            if resp.status != 200:
                body = await resp.text()
                raise CblTestError(f"Failed to start CBS: {resp.status} - {body}")

    async def get_root_ca_certificate(self) -> bytes:
        """
        Fetch the CBS root CA certificate via REST API.

        :return: Root CA certificate in PEM format as bytes
        :raises CblTestError: If unable to fetch the certificate
        """
        # Use CBS REST API directly - returns clean PEM certificate
        url = f"http://{self.__hostname}:8091/pools/default/certificate"

        async with aiohttp.ClientSession() as session, session.get(url) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise CblTestError(f"Failed to get CBS root CA: {resp.status} - {body}")
            return body.strip().encode("utf-8")
