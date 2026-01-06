import asyncio
import platform
import socket
import subprocess
import tempfile
import time
import zipfile
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from time import sleep
from typing import TypeVar, cast

import aiohttp

T = TypeVar("T")
from urllib.parse import quote_plus, urlparse

import requests
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.exceptions import (
    BucketAlreadyExistsException,
    BucketDoesNotExistException,
    CollectionAlreadyExistsException,
    DocumentNotFoundException,
    QueryIndexAlreadyExistsException,
    ScopeAlreadyExistsException,
)
from couchbase.management.buckets import CreateBucketSettings
from couchbase.management.options import CreatePrimaryQueryIndexOptions
from couchbase.options import ClusterOptions
from couchbase.subdocument import upsert
from opentelemetry.trace import get_tracer

from cbltest.api.error import CblTestError
from cbltest.logging import cbl_warning
from cbltest.utils import _try_n_times
from cbltest.version import VERSION


class CouchbaseServer:
    """
    A class that interacts with a Couchbase Server cluster
    """

    def ensure_cluster_healthy(self, cbs_servers: list["CouchbaseServer"]) -> None:
        """
        Ensures all CBS nodes are in the cluster and healthy.
        Uses credentials from this instance to manage the cluster.

        :param cbs_servers: List of CouchbaseServer instances to check (including self)
        """
        if len(cbs_servers) < 2:
            return

        try:
            resp = self.__http_session.get(
                f"http://{self.__hostname}:8091/pools/default"
            )
            resp.raise_for_status()
            cluster_data = resp.json()
        except Exception as e:
            raise CblTestError(f"Cannot connect to CBS cluster: {e}")

        nodes_in_cluster = cluster_data.get("nodes", [])

        for cbs_node in cbs_servers:
            # Skip self - can't add the primary node to its own cluster
            if cbs_node.hostname == self.__hostname:
                continue

            node_in_cluster = False
            node_needs_recovery = False

            for cluster_node in nodes_in_cluster:
                hostname = cluster_node.get("hostname", "").split(":")[0]
                alt_hostname = (
                    cluster_node.get("alternateAddresses", {})
                    .get("external", {})
                    .get("hostname", "")
                )

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

    def __init__(self, url: str, username: str, password: str):
        self.__tracer = get_tracer(__name__, VERSION)
        with self.__tracer.start_as_current_span("connect_to_couchbase_server"):
            if "://" not in url:
                url = f"couchbase://{url}"

            parsed = urlparse(url)
            self.__hostname = parsed.hostname or parsed.netloc.split(":")[0]
            self.__rest_port = parsed.port or 8091  # Track REST port explicitly

            auth = PasswordAuthenticator(username, password)
            opts = ClusterOptions(auth)
            self.__username = username
            self.__password = password
            self.__cluster = Cluster(url, opts)
            self.__cluster.wait_until_ready(timedelta(seconds=10))

            # Create a reusable HTTP session for REST API calls
            self.__http_session = requests.Session()
            self.__http_session.auth = (username, password)

    @property
    def hostname(self) -> str:
        """
        Gets the hostname of this Couchbase Server instance.

        :return: The hostname
        """
        return self.__hostname

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
            bucket_obj = _try_n_times(10, 1, False, self.__cluster.bucket, bucket)
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

                success = False
                for _ in range(0, 10):
                    try:
                        bucket_obj.scope(scope).collection(name).get("_nonexistent")
                    except DocumentNotFoundException:
                        success = True
                        break
                    except Exception:
                        cbl_warning(
                            f"{bucket}.{scope}.{name} appears to not be ready yet, waiting for 1 second..."
                        )
                        sleep(1.0)

                if not success:
                    raise CblTestError(
                        f"Unable to properly create {bucket}.{scope}.{name} in Couchbase Server"
                    )

    def create_bucket(self, name: str, num_replicas: int = 0):
        """
        Creates a bucket with a given name that Sync Gateway can use

        :param name: The name of the bucket to create
        :param num_replicas: The number of replicas for the bucket (default 0)
        """
        with self.__tracer.start_as_current_span(
            "create_bucket", attributes={"cbl.bucket.name": name}
        ):
            mgr = self.__cluster.buckets()
            settings = CreateBucketSettings(
                name=name,
                flush_enabled=True,
                ram_quota_mb=512,
                num_replicas=num_replicas,
            )
            try:
                mgr.create_bucket(settings)
            except BucketAlreadyExistsException:
                pass

    def drop_bucket(self, name: str):
        """
        Drops a bucket from the Couchbase cluster

        :param name: The name of the bucket to drop
        """
        with self.__tracer.start_as_current_span(
            "drop_bucket", attributes={"cbl.bucket.name": name}
        ):
            try:
                mgr = self.__cluster.buckets()
                mgr.drop_bucket(name)
            except BucketDoesNotExistException:
                pass

    async def wait_for_bucket_ready(
        self,
        bucket_name: str,
        retries: int = 60,
        interval: float = 2.0,
    ) -> None:
        for _ in range(retries):
            if (
                self.bucket_healthy(bucket_name)
                and self.bucket_kv_responding(bucket_name)
                and self.collections_ready(bucket_name)
            ):
                return
            await asyncio.sleep(interval)
        raise TimeoutError(f"Bucket {bucket_name} did not become ready")

    def bucket_healthy(self, bucket_name: str) -> bool:
        """
        Returns True only if the bucket is healthy on all nodes.
        """
        resp = self.__http_session.get(
            f"http://{self.__hostname}:8091/pools/default/buckets/{bucket_name}"
        )
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
        resp = self.__http_session.get(
            f"http://{self.__hostname}:8091/pools/default/buckets/{bucket_name}/scopes"
        )
        return resp.status_code == 200

    def get_bucket_names(self) -> list[str]:
        """
        Gets the names of all buckets in the Couchbase cluster

        :return: A list of bucket names
        """
        with self.__tracer.start_as_current_span("get_bucket_names"):
            buckets_resp = self.__http_session.get(
                f"http://{self.__hostname}:8091/pools/default/buckets"
            )
            buckets_resp.raise_for_status()
            buckets_data = buckets_resp.json()
            return [bucket["name"] for bucket in buckets_data]

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
        with self.__tracer.start_as_current_span(
            "wait_for_bucket_deleted", attributes={"cbl.bucket.name": bucket_name}
        ):
            for _ in range(max_retries):
                try:
                    # If bucket no longer exists, deletion is complete
                    if not self.bucket_healthy(bucket_name):
                        return
                except Exception:
                    # Treat errors as "bucket gone"
                    return
                await asyncio.sleep(retry_delay)

            raise CblTestError(
                f"Bucket '{bucket_name}' was not deleted after "
                f"{max_retries * retry_delay} seconds"
            )

    def restore_bucket(
        self,
        name: str,
        tools_path: Path,
        dataset_path: Path,
        dataset_name: str,
        *,
        tools_version: str = "7.6.7",
        repo_name: str | None = None,
    ) -> None:
        """
        Restores a bucket from a backup source

        :param name: The name of the bucket to restore
        :param backup_source: The path to the backup source
        """
        with self.__tracer.start_as_current_span(
            "restore_bucket",
            attributes={"cbl.bucket.name": name, "cbl.backup.source": dataset_name},
        ):
            bin_name = (
                "cbbackupmgr.exe" if platform.system() == "Windows" else "cbbackupmgr"
            )
            cbbackupmgr_path = tools_path / "cbbackupmgr" / tools_version / bin_name
            if not cbbackupmgr_path.exists():
                raise FileNotFoundError(
                    "cbbackupmgr not found, please download it with the environment/aws/download_tool script"
                )

            # For historical reasons, dataset_path is pointing to the Sync Gateway dataset
            # directory.  This should be changed in the future, but for now to avoid breakage
            # just find the neighboring couchbase-server directory.
            data_filepath = (
                dataset_path / ".." / "couchbase-server" / f"{dataset_name}.zip"
            )
            if not data_filepath.exists():
                raise FileNotFoundError(f"Data file {dataset_name}.zip not found!")

            with tempfile.TemporaryDirectory(prefix="cbl_backup_") as tmpdir:
                extract_path = Path(tmpdir)
                try:
                    with zipfile.ZipFile(data_filepath, "r") as zf:
                        zf.extractall(extract_path)
                except zipfile.BadZipFile as e:
                    raise CblTestError(
                        f"Backup zip '{data_filepath}' is invalid: {e}"
                    ) from e

                subprocess.run(
                    [
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
                    ],
                    check=True,
                )

    def indexes_count(self, bucket: str) -> int:
        """
        Returns the number of indexes that are in the specified bucket

        :param bucket: The bucket to check for indexes
        """
        with self.__tracer.start_as_current_span(
            "indexes_count", attributes={"cbl.bucket.name": bucket}
        ):
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
        with self.__tracer.start_as_current_span(
            "run_query", attributes={"cbl.query.name": actual_query}
        ):
            query_obj = self.__cluster.query(actual_query)
            try:
                self.__cluster.query_indexes().create_primary_index(
                    bucket,
                    CreatePrimaryQueryIndexOptions(
                        scope_name=scope, collection_name=collection
                    ),
                )
            except QueryIndexAlreadyExistsException:
                pass

            return list(dict(result) for result in query_obj.execute())

    def upsert_document(
        self,
        bucket: str,
        doc_id: str,
        document: dict,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Inserts a document into the specified bucket.scope.collection.

        :param bucket: The bucket name.
        :param scope: The scope name.
        :param collection: The collection name.
        :param doc_id: The document ID.
        :param document: The document content (a dictionary).
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
            try:
                bucket_obj = _try_n_times(10, 1, False, self.__cluster.bucket, bucket)
                coll = bucket_obj.scope(scope).collection(collection)
                coll.upsert(doc_id, document)
            except Exception as e:
                raise CblTestError(
                    f"Failed to insert document '{doc_id}' into {bucket}.{scope}.{collection}: {e}"
                )

    def delete_document(
        self,
        bucket: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Deletes a document from the specified bucket.scope.collection.
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
            try:
                bucket_obj = _try_n_times(10, 1, False, self.__cluster.bucket, bucket)
                coll = bucket_obj.scope(scope).collection(collection)
                coll.remove(doc_id)
            except DocumentNotFoundException:
                pass
            except Exception as e:
                raise CblTestError(
                    f"Failed to delete document '{doc_id}' from {bucket}.{scope}.{collection}: {e}"
                )

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
                bucket_obj = _try_n_times(10, 1, False, self.__cluster.bucket, bucket)
                coll = bucket_obj.scope(scope).collection(collection)
                result = coll.get(doc_id)
                return result.content_as[dict] if result else None
            except DocumentNotFoundException:
                return None
            except Exception as e:
                raise CblTestError(
                    f"Failed to get document '{doc_id}' from {bucket}.{scope}.{collection}: {e}"
                )

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
            try:
                col = self.__cluster.bucket(bucket).scope(scope).collection(collection)
                col.mutate_in(
                    doc_id,
                    [upsert(xattr_key, xattr_value, xattr=True, create_parents=True)],
                )
            except Exception as e:
                raise CblTestError(
                    f"Failed to upsert xattr '{xattr_key}' on document '{doc_id}' in {bucket}.{scope}.{collection}: {e}"
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
            try:
                from couchbase.subdocument import remove

                col = self.__cluster.bucket(bucket).scope(scope).collection(collection)
                col.mutate_in(
                    doc_id,
                    [remove(xattr_key, xattr=True)],
                )
            except Exception:
                pass

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
            resp = self.__http_session.get(
                f"http://{self.__hostname}:8091/pools/default/remoteClusters"
            )
            resp.raise_for_status()
            resp_body = resp.json()
            remote_cluster_uuid: str | None = None
            for cluster in resp_body:
                if (
                    "name" in cluster
                    and cast(str, cluster["name"]) == target.__hostname
                ):
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
                resp = self.__http_session.get(
                    f"http://{self.__hostname}:8091/pools/default/tasks"
                )
                resp.raise_for_status()
                for task in resp.json():
                    if "type" in task and task["type"] == "xdcr":
                        if "id" in task:
                            id = task["id"]
                            if (
                                id
                                == f"{remote_cluster_uuid}/{bucket_name}/{bucket_name}"
                            ):
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
            resp = self.__http_session.get(
                f"http://{self.__hostname}:8091/pools/default/remoteClusters"
            )
            resp.raise_for_status()
            resp_body = resp.json()
            remote_cluster_uuid: str | None = None
            for cluster in resp_body:
                if (
                    "name" in cluster
                    and cast(str, cluster["name"]) == target.__hostname
                ):
                    remote_cluster_uuid = cluster["uuid"]
                    break

            if remote_cluster_uuid is None:
                return

            # See if the XDCR already exists
            resp = self.__http_session.get(
                f"http://{self.__hostname}:8091/pools/default/tasks"
            )
            resp.raise_for_status()
            xdcr_id: str | None = None
            for task in resp.json():
                if "type" in task and task["type"] == "xdcr":
                    if "id" in task:
                        id = task["id"]
                        if id == f"{remote_cluster_uuid}/{bucket_name}/{bucket_name}":
                            xdcr_id = id
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
                # Set alternate address so external clients can connect via public IP
                # This is critical for AWS VPC where nodes use private IPs internally
                try:
                    self.__http_session.put(
                        f"http://{node_to_add.__hostname}:8091/node/controller/setupAlternateAddresses/external",
                        data={"hostname": node_to_add.__hostname, "mgmt": "8091"},
                    ).raise_for_status()
                    span.add_event(
                        "alternate_address_set",
                        attributes={"hostname": node_to_add.__hostname},
                    )
                except Exception as e:
                    # Node is already added to cluster, but external SDK connections may fail
                    # Common causes: Node not fully initialized, auth issues, network problems
                    cbl_warning(
                        f"Failed to set alternate address for {node_to_add.__hostname}: {e}. "
                        f"Node added successfully, but external SDK connections (from TDK) may fail. "
                        f"Internal cluster communication will work normally."
                    )
                    span.add_event(
                        "alternate_address_failed", attributes={"error": str(e)}
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
                    alt_hostname = (
                        node.get("alternateAddresses", {})
                        .get("external", {})
                        .get("hostname", "")
                    )

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

            self._retry(
                do_rebalance, max_attempts=5, wait_seconds=1, operation_name="Rebalance"
            )

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
                    cbl_warning(
                        f"{operation_name} failed (attempt {attempt + 1}/{max_attempts}): {e}"
                    )
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

    def _find_node_otp(
        self, pool_data: dict, target_node: "CouchbaseServer", operation: str
    ) -> str:
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
        raise CblTestError(
            f"Node {target_node.hostname} not found in cluster for {operation}"
        )

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

    def wait_for_cluster_healthy(
        self, timeout: int = 60, check_interval: int = 2
    ) -> bool:
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
                resp = self.__http_session.get(
                    f"http://{self.__hostname}:8091/pools/default"
                )
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
                buckets_resp = self.__http_session.get(
                    f"http://{self.__hostname}:8091/pools/default/buckets"
                )
                buckets_resp.raise_for_status()

                all_buckets_healthy = True
                for bucket in buckets_resp.json():
                    vbucket_map = bucket.get("vBucketServerMap", {})
                    if not vbucket_map.get("serverList") or not vbucket_map.get(
                        "vBucketMap"
                    ):
                        all_buckets_healthy = False
                        break

                    # Check all vBuckets have active nodes
                    if any(
                        not vb or vb[0] == -1
                        for vb in vbucket_map.get("vBucketMap", [])
                    ):
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
            resp = self.__http_session.get(
                f"http://{self.__hostname}:8091/pools/default/rebalanceProgress"
            )
            resp.raise_for_status()
            status = resp.json()

            if status.get("status") == "none":
                return
            time.sleep(10)

        raise CblTestError(
            f"Rebalance did not complete within {timeout_seconds} seconds"
        )

    async def reconfigure_ports(
        self,
        rest_port: int = 9000,
        ssl_port: int = 1900,
        memcached_port: int = 9050,
        memcached_ssl_port: int = 9057,
    ) -> None:
        """
        Reconfigure CBS ports by calling shell2http endpoint on the CBS node.

        :param rest_port: New REST API port (default 9000)
        :param ssl_port: New SSL REST port (default 1900)
        :param memcached_port: New memcached port (default 9050)
        :param memcached_ssl_port: New SSL memcached port (default 9057)
        """
        shell2http_url = (
            f"http://{self.hostname}:20001/configure-cbs-ports"
            f"?rest_port={rest_port}"
            f"&ssl_port={ssl_port}"
            f"&memcached_port={memcached_port}"
            f"&memcached_ssl_port={memcached_ssl_port}"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(shell2http_url) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise CblTestError(
                        f"Failed to reconfigure CBS ports: {resp.status} - {body}"
                    )

    async def stop_server(self) -> None:
        """
        Stop the Couchbase Server service via shell2http.
        """
        shell2http_url = f"http://{self.__hostname}:20001/stop-cbs"

        async with aiohttp.ClientSession() as session:
            async with session.get(shell2http_url) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise CblTestError(f"Failed to stop CBS: {resp.status} - {body}")

    async def start_server(self) -> None:
        """
        Start the Couchbase Server service via shell2http.
        """
        shell2http_url = f"http://{self.__hostname}:20001/start-cbs"

        async with aiohttp.ClientSession() as session:
            async with session.get(shell2http_url) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise CblTestError(f"Failed to start CBS: {resp.status} - {body}")

    async def reset_cluster(self) -> None:
        """
        Reset the Couchbase cluster via shell2http (removes all data and configuration).
        """
        shell2http_url = f"http://{self.__hostname}:20001/reset-cluster"

        async with aiohttp.ClientSession() as session:
            async with session.get(shell2http_url) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise CblTestError(
                        f"Failed to reset CBS cluster: {resp.status} - {body}"
                    )

    async def wait_for_server_ready(
        self,
        timeout: int = 120,
        port: int = 8091,
        check_interval: float = 1.0,
    ) -> None:
        """
        Robust wait for Couchbase Server readiness.

        Readiness definition:
        1. TCP port is accepting connections
        2. /pools/default returns HTTP 200

        :param timeout: Total timeout in seconds
        :param port: REST API port to check
        :param check_interval: Sleep interval between checks
        """
        start_time = time.time()
        hostname = self.__hostname
        url = f"http://{hostname}:{port}/pools/default"

        last_error: Exception | str | None = None

        while time.time() - start_time < timeout:
            try:
                with socket.create_connection((hostname, port), timeout=2):
                    pass
            except Exception as e:
                last_error = e
                await asyncio.sleep(check_interval)
                continue

            try:
                resp = self.__http_session.get(url, timeout=5)
                if resp.status_code == 200:
                    return
                else:
                    last_error = RuntimeError(
                        f"REST not ready: HTTP {resp.status_code}"
                    )
            except requests.exceptions.ConnectionError as e:
                last_error = f"REST connection error: {e}"
            except requests.exceptions.ReadTimeout as e:
                last_error = f"REST timeout: {e}"
            except ValueError as e:
                last_error = f"Invalid JSON from REST: {e}"

            await asyncio.sleep(check_interval)

        raise CblTestError(
            f"CBS did not become ready on {hostname}:{port} within {timeout}s. "
            f"Last error: {last_error}"
        )

    async def wait_for_server_stopped(self, timeout: int = 60) -> None:
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = self.__http_session.get(
                    f"http://{self.__hostname}:{self.__rest_port}/pools/default",
                    timeout=2,
                )
                if resp.status_code != 200:
                    return
            except Exception:
                return
            await asyncio.sleep(1)

        raise CblTestError("CBS did not stop cleanly within timeout")

    def init_cluster(self, rest_port: int = 8091) -> None:
        """
        Initialize the CBS cluster with basic settings.

        :param rest_port: REST API port to use (default 8091)
        """
        with self.__tracer.start_as_current_span("init_cluster"):
            # Use the specified REST port for HTTP calls
            base_url = f"http://{self.__hostname}:{rest_port}"

            # Initialize cluster if not already done
            resp = self.__http_session.post(
                f"{base_url}/clusterInit",
                data={
                    "clusterName": "test-cluster",
                    "username": self.__username,
                    "password": self.__password,
                    "port": str(rest_port),
                    "services": "kv,index,n1ql",
                },
            )
            # 200 = success, 400 = already initialized
            if resp.status_code not in [200, 400]:
                raise CblTestError(
                    f"Failed to initialize cluster: {resp.status_code} - {resp.text}"
                )

    async def wait_for_kv_ready(self, timeout: int = 60) -> None:
        """
        Wait for KV (data) service to be ready.

        :param timeout: Maximum time to wait in seconds
        """
        for attempt in range(timeout):
            try:
                # Check if we can connect to the data service
                resp = self.__http_session.get(
                    f"http://{self.__hostname}:{self.__rest_port}/pools/default/buckets"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Check if any node has KV service available
                    nodes = data.get("nodes", [])
                    if nodes:
                        # If we can get pool info, KV service is likely ready
                        return
            except Exception:
                pass

            if attempt % 10 == 0:
                print(f"Waiting for KV service... ({attempt}/{timeout})")
            await asyncio.sleep(1)

        raise CblTestError(f"KV service did not become ready within {timeout} seconds")

    def assert_ports_applied(
        self, rest_port: int = 8091, memcached_port: int = 11211
    ) -> None:
        """
        Verify that CBS is actually listening on the expected ports.

        :param rest_port: Expected REST API port
        :param memcached_port: Expected memcached port
        """
        with self.__tracer.start_as_current_span("assert_ports_applied"):
            # Check REST port
            try:
                resp = self.__http_session.get(
                    f"http://{self.__hostname}:{rest_port}/pools/default"
                )
                if resp.status_code != 200:
                    raise CblTestError(
                        f"REST port {rest_port} not responding correctly"
                    )
            except Exception as e:
                raise CblTestError(f"Cannot connect to REST port {rest_port}: {e}")

            # Note: Memcached port checking would require different approach
            # as it's binary protocol, not HTTP
            print(f"✓ CBS confirmed listening on REST port {rest_port}")

    def reconnect(self, new_url: str) -> None:
        """
        Reconnect to CBS with a new URL (useful after port changes).

        :param new_url: New CBS URL (e.g., "couchbase://hostname:9000")
        """
        with self.__tracer.start_as_current_span("reconnect_to_couchbase_server"):
            if "://" not in new_url:
                new_url = f"couchbase://{new_url}"

            parsed = urlparse(new_url)
            hostname = parsed.hostname or parsed.netloc.split(":")[0]
            rest_port = parsed.port or 8091

            # Reconnect SDK cluster
            auth = PasswordAuthenticator(self.__username, self.__password)
            opts = ClusterOptions(auth)
            self.__cluster = Cluster(new_url, opts)
            self.__cluster.wait_until_ready(timedelta(seconds=10))

            # Update hostname, REST port, and recreate HTTP session
            self.__hostname = hostname
            self.__rest_port = rest_port
            self.__http_session = requests.Session()
            self.__http_session.auth = (self.__username, self.__password)
